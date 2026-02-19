"""Marketing Project Service — business logic for project operations.

Extracts orchestration logic from routes: approval submission, access control,
file uploads, and AI-powered budget distribution / OKR suggestions.
Routes call this service; the service coordinates repositories and side effects.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from marketing.repositories import (
    ProjectRepository, MemberRepository, BudgetRepository, ActivityRepository,
)

logger = logging.getLogger('jarvis.marketing.services.project')

VALID_STATUS_TRANSITIONS = {
    'submit_approval': ('draft', 'cancelled', 'pending_approval'),
    'activate': ('approved',),
    'pause': ('active',),
    'complete': ('active', 'paused'),
}


@dataclass
class UserContext:
    """Lightweight user context passed from route handlers."""
    user_id: int
    company: Optional[str] = None


@dataclass
class ServiceResult:
    """Result of a service operation."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    status_code: int = 200


class ProjectService:
    """Orchestrates marketing project business logic."""

    def __init__(self):
        self.project_repo = ProjectRepository()
        self.member_repo = MemberRepository()
        self.budget_repo = BudgetRepository()
        self.activity_repo = ActivityRepository()

    # ============== Public Methods ==============

    def can_access_project(self, project: Dict, user_id: int, scope: str,
                           user_company: Optional[str] = None) -> bool:
        """Check if user can access a project given their permission scope.

        Checks: scope=all, owner, team member, pending approver, department match.
        """
        if scope == 'all':
            return True
        if project.get('owner_id') == user_id:
            return True
        members = self.member_repo.get_by_project(project['id'])
        if any(m['user_id'] == user_id for m in members):
            return True
        if self._is_pending_approver(project['id'], user_id):
            return True
        if scope == 'department' and user_company:
            if project.get('company_id') == int(user_company):
                return True
        return False

    def submit_approval(self, project_id: int, user: UserContext,
                        approver_id: Optional[int] = None) -> ServiceResult:
        """Submit project for approval via approval engine.

        Orchestrates: validation -> context building -> engine.submit() ->
                      status update -> notifications.
        """
        project = self.project_repo.get_by_id(project_id)
        if not project:
            return ServiceResult(success=False, error='Project not found', status_code=404)

        if project['status'] not in VALID_STATUS_TRANSITIONS['submit_approval']:
            return ServiceResult(
                success=False,
                error=f"Cannot submit from status '{project['status']}'",
                status_code=400,
            )

        try:
            from core.approvals.engine import ApprovalEngine
            engine = ApprovalEngine()

            context = self._build_approval_context(project, project_id, approver_id)

            result = engine.submit(
                entity_type='mkt_project',
                entity_id=project_id,
                context=context,
                requested_by=user.user_id,
            )

            self.project_repo.update_status(project_id, 'pending_approval')
            self.activity_repo.log(project_id, 'approval_submitted', actor_id=user.user_id)

            self._notify_project_members(
                project_id, user.user_id,
                title=f"Project '{project['name']}' submitted for approval",
            )

            request_id = result.get('request_id') if isinstance(result, dict) else result
            return ServiceResult(success=True, data={
                'success': True, 'request_id': request_id,
            })

        except Exception as e:
            logger.error(f"Approval submission failed: {e}", exc_info=True)
            return ServiceResult(success=False, error=str(e), status_code=500)

    def upload_file(self, project_id: int, file_bytes: bytes, filename: str,
                    description: str, user_id: int) -> ServiceResult:
        """Upload file to Google Drive and attach to project.

        Orchestrates: validation -> folder structure -> Drive upload ->
                      DB record -> activity log.
        """
        if len(file_bytes) > 10 * 1024 * 1024:
            return ServiceResult(success=False, error='File exceeds 10 MB limit', status_code=400)

        proj = self.project_repo.get_by_id(project_id)
        if not proj:
            return ServiceResult(success=False, error='Project not found', status_code=404)

        try:
            from core.services.drive_service import get_drive_service, find_or_create_folder, ROOT_FOLDER_ID

            project_name = proj.get('name', f'Project-{project_id}')
            clean_name = ''.join(
                c for c in project_name if c.isalnum() or c in ' -_'
            ).strip() or f'Project-{project_id}'

            try:
                service = get_drive_service()
            except FileNotFoundError:
                return ServiceResult(
                    success=False,
                    error='Google Drive is not configured. Set up credentials in Settings > Connectors.',
                    status_code=503,
                )

            mkt_folder = find_or_create_folder(service, 'Marketing', ROOT_FOLDER_ID)
            proj_folder = find_or_create_folder(service, clean_name, mkt_folder)

            ext, mime_type = self._detect_mime(filename)

            from googleapiclient.http import MediaIoBaseUpload
            import io as iomod
            media = MediaIoBaseUpload(iomod.BytesIO(file_bytes), mimetype=mime_type, resumable=True)
            drive_file = service.files().create(
                body={'name': filename, 'parents': [proj_folder]},
                media_body=media,
                fields='id, webViewLink',
                supportsAllDrives=True,
            ).execute()
            drive_link = drive_file.get(
                'webViewLink', f"https://drive.google.com/file/d/{drive_file['id']}/view"
            )

            from marketing.repositories import FileRepository
            file_repo = FileRepository()
            file_id = file_repo.create(
                project_id, filename, drive_link, user_id,
                file_type=ext or None,
                mime_type=mime_type,
                file_size=len(file_bytes),
                description=description or None,
            )
            self.activity_repo.log(project_id, 'file_attached', actor_id=user_id,
                                   details={'file_name': filename})

            return ServiceResult(success=True, data={
                'success': True, 'id': file_id,
                'drive_link': drive_link,
                'file_name': filename,
                'file_size': len(file_bytes),
            }, status_code=201)

        except Exception as e:
            logger.exception('File upload failed')
            return ServiceResult(success=False, error=str(e), status_code=500)

    def ai_distribute_budget(self, total_budget: float, audience_size: int,
                             lead_to_sale_rate: float, active_channels: Dict,
                             benchmarks: List[Dict]) -> ServiceResult:
        """Use AI to distribute budget across channels like a PPC specialist.

        Orchestrates: channel info building -> prompt construction ->
                      LLM call -> response validation.
        """
        if not total_budget or not benchmarks:
            return ServiceResult(success=False, error='total_budget and benchmarks required', status_code=400)

        channel_info = self._build_channel_info(benchmarks)
        active_info = {
            key: channel_info[key]
            for stage, keys in active_channels.items()
            for key in keys
            if key in channel_info
        }
        if not active_info:
            return ServiceResult(success=False, error='No active channels', status_code=400)

        system_prompt = self._build_distribution_prompt(total_budget, audience_size, active_info)

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

            if isinstance(allocations, dict) and 'reasoning' in allocations:
                del allocations['reasoning']

            total = sum(allocations.values()) if isinstance(allocations, dict) else 0

            return ServiceResult(success=True, data={
                'success': True,
                'allocations': allocations,
                'reasoning': reasoning,
                'total_allocated': total,
                'tokens_used': 0,
            })

        except ImportError:
            return ServiceResult(success=False, error='AI provider not available', status_code=503)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"AI distribute JSON parse error: {e}")
            return ServiceResult(success=False, error='Failed to parse AI response', status_code=500)
        except Exception as e:
            logger.error(f"AI distribute error: {e}")
            return ServiceResult(success=False, error=str(e), status_code=500)

    def suggest_key_results(self, project_id: int,
                            objective_id: int) -> ServiceResult:
        """Use AI to suggest key results for an objective.

        Orchestrates: data fetch -> prompt building -> LLM call ->
                      result validation + KPI linking.
        """
        from database import get_db, get_cursor, release_db
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute(
                'SELECT title FROM mkt_objectives WHERE id = %s AND project_id = %s',
                (objective_id, project_id),
            )
            obj_row = cursor.fetchone()
            if not obj_row:
                return ServiceResult(success=False, error='Objective not found', status_code=404)
            obj_title = obj_row['title']

            cursor.execute('''
                SELECT pk.id, kd.name, pk.current_value, pk.target_value, kd.unit
                FROM mkt_project_kpis pk
                JOIN mkt_kpi_definitions kd ON pk.kpi_definition_id = kd.id
                WHERE pk.project_id = %s
            ''', (project_id,))
            kpis = [dict(r) for r in cursor.fetchall()]
        finally:
            release_db(conn)

        prompt = self._build_kr_suggestion_prompt(obj_title, kpis)

        try:
            from ai_agent.services.ai_agent_service import AIAgentService
            svc = AIAgentService()
            model_config = svc.model_config_repo.get_default()
            if not model_config:
                return ServiceResult(success=False, error='No AI model configured', status_code=503)

            provider = svc.get_provider(model_config.provider.value)
            result = provider.generate_structured(
                model_name=model_config.model_name,
                messages=[{'role': 'user', 'content': prompt}],
                max_tokens=1024,
                temperature=0.5,
                system='You are a marketing OKR assistant. Return ONLY valid JSON arrays.',
            )
            suggestions = result if isinstance(result, list) else []

            valid_kpi_ids = {k['id'] for k in kpis}
            validated = []
            for s in suggestions[:5]:
                if not isinstance(s, dict) or not s.get('title'):
                    continue
                kpi_id = s.get('linked_kpi_id')
                if kpi_id and kpi_id not in valid_kpi_ids:
                    kpi_id = None
                validated.append({
                    'title': str(s['title']),
                    'target_value': float(s.get('target_value', 100)),
                    'unit': s.get('unit', 'number') if s.get('unit') in ('number', 'currency', 'percentage') else 'number',
                    'linked_kpi_id': kpi_id,
                })

            return ServiceResult(success=True, data={'suggestions': validated})

        except Exception as e:
            logger.warning(f'AI suggest KRs failed: {e}')
            return ServiceResult(success=False, error=str(e), status_code=500)

    # ============== Private Helpers ==============

    def _is_pending_approver(self, project_id: int, user_id: int) -> bool:
        """Check if user has a pending approval request for this project."""
        from database import get_db, get_cursor, release_db
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                SELECT 1 FROM approval_requests
                WHERE entity_type = 'mkt_project' AND entity_id = %s
                  AND status IN ('pending', 'on_hold')
                  AND (context_snapshot->>'approver_user_id')::int = %s
                LIMIT 1
            ''', (project_id, user_id))
            return cursor.fetchone() is not None
        finally:
            release_db(conn)

    def _build_approval_context(self, project: Dict, project_id: int,
                                approver_id: Optional[int] = None) -> Dict:
        """Build context snapshot for approval engine."""
        budget_lines = self.budget_repo.get_lines_by_project(project_id)
        context = {
            'title': project['name'],
            'amount': float(project['total_budget']),
            'currency': project['currency'],
            'project_type': project['project_type'],
            'company': project.get('company_name', ''),
            'brand': project.get('brand_name', ''),
            'owner': project.get('owner_name', ''),
            'channels': project.get('channel_mix', []),
            'start_date': str(project.get('start_date', '')),
            'end_date': str(project.get('end_date', '')),
            'objective': project.get('objective', ''),
            'budget_breakdown': [
                {'channel': l['channel'], 'amount': float(l['planned_amount'])}
                for l in budget_lines
            ],
        }

        stakeholder_ids = self.member_repo.get_stakeholder_ids(project_id)
        if stakeholder_ids:
            context['stakeholder_approver_ids'] = stakeholder_ids
            if project.get('approval_mode') == 'all':
                context['min_approvals_override'] = len(stakeholder_ids)
        elif approver_id:
            context['approver_user_id'] = int(approver_id)

        return context

    def _notify_project_members(self, project_id: int, exclude_user_id: int,
                                title: str):
        """Send in-app notification to all project members except the actor."""
        try:
            from core.notifications.notify import notify_users
            member_ids = self.member_repo.get_user_ids_for_project(project_id)
            notify_users(
                [uid for uid in member_ids if uid != exclude_user_id],
                title=title,
                link=f'/app/marketing/projects/{project_id}',
                entity_type='mkt_project',
                entity_id=project_id,
                type='info',
            )
        except Exception:
            pass

    def _build_channel_info(self, benchmarks: List[Dict]) -> Dict:
        """Transform benchmark list into channel info dict for AI prompt."""
        channel_info = {}
        for bm in benchmarks:
            key = bm['channel_key']
            if key not in channel_info:
                channel_info[key] = {
                    'label': bm['channel_label'],
                    'stage': bm['funnel_stage'],
                    'months': {},
                }
            channel_info[key]['months'][bm['month_index']] = {
                'cpc': bm['cpc'],
                'cvr_lead': bm['cvr_lead'],
                'cvr_car': bm['cvr_car'],
            }
        return channel_info

    def _build_distribution_prompt(self, total_budget: float, audience_size: int,
                                   active_info: Dict) -> str:
        """Build the system prompt for AI budget distribution."""
        return f"""You are the best digital marketing PPC specialist in the Romanian automotive market.
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

    def _build_kr_suggestion_prompt(self, obj_title: str, kpis: List[Dict]) -> str:
        """Build prompt for AI key result suggestions."""
        kpi_list = ''
        if kpis:
            kpi_lines = [
                f'- ID:{k["id"]} "{k["name"]}" '
                f'(current: {k["current_value"]}, target: {k["target_value"]}, unit: {k["unit"]})'
                for k in kpis
            ]
            kpi_list = '\n\nAvailable project KPIs that can be linked:\n' + '\n'.join(kpi_lines)

        return f'''Given this marketing objective: "{obj_title}"{kpi_list}

Suggest 3-5 measurable key results. For each provide:
- title: concise measurable outcome
- target_value: realistic target number
- unit: "number" or "currency" or "percentage"
- linked_kpi_id: ID from the KPI list above if one matches, else null

Return ONLY a JSON array:
[{{"title": "...", "target_value": 100, "unit": "number", "linked_kpi_id": null}}]'''

    @staticmethod
    def _detect_mime(filename: str) -> tuple:
        """Detect file extension and MIME type."""
        ext = filename.lower().rsplit('.', 1)[-1] if '.' in filename else ''
        mime_map = {
            'pdf': 'application/pdf', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
            'png': 'image/png', 'doc': 'application/msword',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'xls': 'application/vnd.ms-excel',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'ppt': 'application/vnd.ms-powerpoint',
            'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        }
        return ext, mime_map.get(ext, 'application/octet-stream')
