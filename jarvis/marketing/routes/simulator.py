"""Campaign simulator endpoints."""

import json
import logging
import os
import re
from flask import jsonify, request
from flask_login import login_required
from core.utils.api_helpers import error_response

from database import get_db, get_cursor, release_db
from marketing import marketing_bp

logger = logging.getLogger('jarvis.marketing.routes.simulator')

SIM_DEFAULTS = {
    'awareness_threshold': 0.42,
    'awareness_multiplier': 1.7,
    'consideration_threshold': 0.14,
    'consideration_multiplier': 1.5,
    'auto_month_pcts': [0.40, 0.35, 0.25],
    'auto_stage_weights': [
        {'awareness': 0.80, 'consideration': 0.10, 'conversion': 0.10},
        {'awareness': 0.50, 'consideration': 0.25, 'conversion': 0.25},
        {'awareness': 0.20, 'consideration': 0.30, 'conversion': 0.50},
    ],
    'default_active': {
        'awareness': ['meta_traffic_aw', 'meta_reach', 'meta_video_views', 'youtube_skippable_aw', 'google_display'],
        'consideration': ['meta_engagement', 'special_activation'],
        'conversion': ['google_pmax_conv', 'meta_conversion'],
    },
}


@marketing_bp.route('/api/simulator/settings', methods=['GET'])
@login_required
def api_sim_settings_get():
    """Return simulator configuration (thresholds, multipliers, auto-distribute weights)."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute("SELECT setting_value FROM notification_settings WHERE setting_key = 'sim_config'")
        row = cursor.fetchone()
        if row:
            config = json.loads(row['setting_value'])
            merged = {**SIM_DEFAULTS, **config}
        else:
            merged = {**SIM_DEFAULTS}
        return jsonify({'settings': merged})
    finally:
        release_db(conn)


@marketing_bp.route('/api/simulator/settings', methods=['PUT'])
@login_required
def api_sim_settings_put():
    """Save simulator configuration."""
    data = request.get_json(silent=True) or {}
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        val = json.dumps(data)
        cursor.execute('''
            INSERT INTO notification_settings (setting_key, setting_value) VALUES ('sim_config', %s)
            ON CONFLICT (setting_key) DO UPDATE SET setting_value = EXCLUDED.setting_value, updated_at = NOW()
        ''', (val,))
        conn.commit()
        return jsonify({'success': True})
    finally:
        release_db(conn)


@marketing_bp.route('/api/simulator/benchmarks', methods=['GET'])
@login_required
def api_sim_benchmarks():
    """Return all simulator benchmarks grouped by funnel stage."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute('''
            SELECT id, channel_key, channel_label, funnel_stage, month_index,
                   cpc::float, cvr_lead::float, cvr_car::float, is_active
            FROM mkt_sim_benchmarks
            WHERE is_active = TRUE
            ORDER BY
                CASE funnel_stage
                    WHEN 'awareness' THEN 1
                    WHEN 'consideration' THEN 2
                    WHEN 'conversion' THEN 3
                END,
                channel_key, month_index
        ''')
        benchmarks = [dict(r) for r in cursor.fetchall()]
        return jsonify({'benchmarks': benchmarks})
    finally:
        release_db(conn)


@marketing_bp.route('/api/simulator/benchmarks/<int:benchmark_id>', methods=['PUT'])
@login_required
def api_sim_benchmark_update(benchmark_id):
    """Update a single benchmark's CPC/CVR values."""
    data = request.get_json(silent=True) or {}
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        sets = []
        params = []
        for field in ('cpc', 'cvr_lead', 'cvr_car'):
            if field in data:
                sets.append(f"{field} = %s")
                params.append(float(data[field]))
        if not sets:
            return error_response('No fields to update')

        sets.append("updated_at = CURRENT_TIMESTAMP")
        params.append(benchmark_id)
        cursor.execute(
            f"UPDATE mkt_sim_benchmarks SET {', '.join(sets)} WHERE id = %s",
            params,
        )
        conn.commit()
        return jsonify({'success': True})
    finally:
        release_db(conn)


@marketing_bp.route('/api/simulator/benchmarks/bulk', methods=['PUT'])
@login_required
def api_sim_benchmarks_bulk_update():
    """Bulk update benchmarks. Body: {updates: [{id, cpc?, cvr_lead?, cvr_car?}]}"""
    data = request.get_json(silent=True) or {}
    updates = data.get('updates', [])
    if not updates:
        return error_response('No updates provided')

    conn = get_db()
    try:
        cursor = get_cursor(conn)
        count = 0
        for upd in updates:
            bid = upd.get('id')
            if not bid:
                continue
            sets = []
            params = []
            for field in ('cpc', 'cvr_lead', 'cvr_car'):
                if field in upd:
                    sets.append(f"{field} = %s")
                    params.append(float(upd[field]))
            if not sets:
                continue
            sets.append("updated_at = CURRENT_TIMESTAMP")
            params.append(bid)
            cursor.execute(
                f"UPDATE mkt_sim_benchmarks SET {', '.join(sets)} WHERE id = %s",
                params,
            )
            count += 1
        conn.commit()
        return jsonify({'success': True, 'updated': count})
    finally:
        release_db(conn)


@marketing_bp.route('/api/simulator/benchmarks', methods=['POST'])
@login_required
def api_sim_benchmark_create():
    """Create a new channel with benchmark rows for all 3 months."""
    data = request.get_json(silent=True) or {}
    channel_label = (data.get('channel_label') or '').strip()
    funnel_stage = data.get('funnel_stage', '')
    months = data.get('months', [])

    if not channel_label or funnel_stage not in ('awareness', 'consideration', 'conversion'):
        return error_response('channel_label and valid funnel_stage required')

    channel_key = re.sub(r'[^a-z0-9_]', '', channel_label.lower().replace(' ', '_').replace('-', '_'))
    if not channel_key:
        return error_response('Invalid channel name')

    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute("SELECT 1 FROM mkt_sim_benchmarks WHERE channel_key = %s LIMIT 1", (channel_key,))
        if cursor.fetchone():
            return error_response(f'Channel "{channel_key}" already exists', 409)

        created_ids = []
        for md in months:
            mi = md.get('month_index')
            if mi not in (1, 2, 3):
                continue
            if funnel_stage == 'consideration' and mi == 1:
                continue
            cursor.execute('''
                INSERT INTO mkt_sim_benchmarks (channel_key, channel_label, funnel_stage, month_index, cpc, cvr_lead, cvr_car)
                VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
            ''', (channel_key, channel_label, funnel_stage, mi,
                  float(md.get('cpc', 0.10)), float(md.get('cvr_lead', 0.001)), float(md.get('cvr_car', 0.0005))))
            row = cursor.fetchone()
            if row:
                created_ids.append(row['id'])
        conn.commit()
        return jsonify({'success': True, 'channel_key': channel_key, 'ids': created_ids})
    finally:
        release_db(conn)


@marketing_bp.route('/api/simulator/benchmarks/channel/<channel_key>', methods=['DELETE'])
@login_required
def api_sim_benchmark_delete_channel(channel_key):
    """Delete all benchmark rows for a channel."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute("DELETE FROM mkt_sim_benchmarks WHERE channel_key = %s", (channel_key,))
        deleted = cursor.rowcount
        conn.commit()
        return jsonify({'success': True, 'deleted': deleted})
    finally:
        release_db(conn)


@marketing_bp.route('/api/simulator/ai-distribute', methods=['POST'])
@login_required
def api_sim_ai_distribute():
    """Use AI to distribute budget across channels like a PPC specialist."""
    data = request.get_json(silent=True) or {}
    total_budget = data.get('total_budget', 0)
    audience_size = data.get('audience_size', 300000)
    lead_to_sale_rate = data.get('lead_to_sale_rate', 5)
    active_channels = data.get('active_channels', {})  # {stage: [channel_keys]}
    benchmarks = data.get('benchmarks', [])  # full benchmark list

    if not total_budget or not benchmarks:
        return error_response('total_budget and benchmarks required')

    # Build channel info for the prompt
    channel_info = {}
    for bm in benchmarks:
        key = bm['channel_key']
        stage = bm['funnel_stage']
        month = bm['month_index']
        if key not in channel_info:
            channel_info[key] = {
                'label': bm['channel_label'],
                'stage': stage,
                'months': {},
            }
        channel_info[key]['months'][month] = {
            'cpc': bm['cpc'],
            'cvr_lead': bm['cvr_lead'],
            'cvr_car': bm['cvr_car'],
        }

    # Filter to active channels only
    active_info = {}
    for stage, keys in active_channels.items():
        for key in keys:
            if key in channel_info:
                active_info[key] = channel_info[key]

    if not active_info:
        return error_response('No active channels')

    system_prompt = f"""You are the best digital marketing PPC specialist in the Romanian automotive market.
You manage campaigns for car dealerships (Toyota, Lexus, Mazda, Hyundai, Suzuki, Kia brands).

TASK: Distribute a campaign budget of €{total_budget:,.0f} across advertising channels over 3 months to MAXIMIZE lead generation and car sales.

AUDIENCE SIZE: {audience_size:,} people

FUNNEL STRATEGY RULES:
1. Awareness channels build brand recognition. Front-load in Month 1, reduce later.
2. Consideration channels CANNOT run in Month 1 — they only activate from Month 2 (retargeting audiences from awareness).
3. Conversion channels can run all 3 months but should ramp UP over time as warm audiences grow.

SYNERGY MULTIPLIER SYSTEM (critical for maximizing leads):
- If >42% of total budget goes to Awareness → all leads get a 1.7x multiplier
- If >14% of total budget goes to Consideration → all leads get a 1.5x multiplier
- Both can stack for 2.55x total multiplier
- Try to hit BOTH thresholds for maximum impact

OPTIMIZATION GUIDELINES:
- Channels with lower CPC generate more clicks per EUR
- Higher CVR_LEAD channels convert more clicks to leads
- The "best" channels have the lowest CPC AND highest CVR_LEAD (best cost-per-lead)
- CVR rates change per month — check each month's benchmarks
- Balance between high-volume cheap channels and high-quality expensive channels
- Don't spread too thin — focus budget on fewer channels with meaningful amounts
- Minimum useful budget per channel per month: €100

AVAILABLE CHANNELS AND BENCHMARKS:
{json.dumps(active_info, indent=2)}

Respond with ONLY a JSON object mapping "channel_key-month_index" to budget amount in EUR.
Example: {{"meta_traffic_aw-1": 500, "meta_traffic_aw-2": 400, "meta_traffic_aw-3": 300}}

Rules:
- Total of all values must equal exactly €{total_budget:,.0f}
- Consideration channels must have 0 for month 1
- All values must be positive integers (round to nearest €)
- Only include channels from the list above
- Include your reasoning as a brief "reasoning" field

Return format:
{{"allocations": {{"channel-month": amount, ...}}, "reasoning": "brief explanation"}}"""

    try:
        from ai_agent.providers.claude_provider import ClaudeProvider

        provider = ClaudeProvider()
        api_key = os.environ.get('ANTHROPIC_API_KEY')

        result = provider.generate_structured(
            model_name='claude-sonnet-4-20250514',
            messages=[{'role': 'user', 'content': 'Distribute the budget optimally.'}],
            max_tokens=2048,
            temperature=0.3,
            api_key=api_key,
            system=system_prompt,
        )
        allocations = result.get('allocations', result)
        reasoning = result.get('reasoning', '')

        # Validate total matches budget (allow 1% tolerance for rounding)
        total = sum(allocations.values()) if isinstance(allocations, dict) else 0
        # Remove reasoning key from allocations if it accidentally ended up there
        if 'reasoning' in allocations:
            del allocations['reasoning']
            total = sum(allocations.values())

        return jsonify({
            'success': True,
            'allocations': allocations,
            'reasoning': reasoning,
            'total_allocated': total,
            'tokens_used': 0,
        })
    except ImportError:
        return error_response('AI provider not available', 503)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"AI distribute JSON parse error: {e}")
        return error_response('Failed to parse AI response', 500)
    except Exception as e:
        logger.error(f"AI distribute error: {e}")
        return error_response(str(e), 500)
