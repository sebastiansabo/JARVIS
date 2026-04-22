"""
e-Factura OAuth2 Authentication API routes.
"""
from flask import request, jsonify, redirect, render_template, session
from flask_login import login_required

from core.utils.api_helpers import safe_error_response, api_login_required
from ._shared import efactura_bp, efactura_access_required, logger
from ..services.oauth_service import get_oauth_service, ANAFOAuthService


def _get_oauth_service_for_cif(cif: str):
    """Get OAuth service with per-company credentials if configured."""
    from ..repositories.company_repo import CompanyConnectionRepository
    company = CompanyConnectionRepository().get_by_cif(cif)
    if company and company.config:
        client_id = company.config.get('client_id')
        client_secret = company.config.get('client_secret')
        redirect_uri = company.config.get('redirect_uri')
        if client_id and client_secret:
            return ANAFOAuthService(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
            )
    return get_oauth_service()


# ============================================================
# API: OAuth2 Authentication
# ============================================================

@efactura_bp.route('/oauth/authorize', methods=['GET'])
@login_required
def oauth_authorize():
    """
    Initiate OAuth2 flow with ANAF.

    Query params:
        cif: Company CIF (required)

    Redirects user to ANAF login page where they authenticate with USB token.
    """
    try:
        cif = request.args.get('cif')

        if not cif:
            return jsonify({
                'success': False,
                'error': "Missing required parameter: cif",
            }), 400

        # Clean CIF (remove RO prefix if present)
        clean_cif = cif.upper().replace('RO', '').strip()

        # Get OAuth service (per-company credentials if configured)
        oauth_service = _get_oauth_service_for_cif(clean_cif)
        auth_url, state = oauth_service.get_authorization_url(clean_cif)

        # Store state in session for callback validation
        session['oauth_state'] = state
        session['oauth_cif'] = clean_cif

        # Store code_verifier and per-company credentials in session for callback
        pending = oauth_service.get_pending_auth(state)
        if pending:
            session['oauth_code_verifier'] = pending['code_verifier']
            session['oauth_created_at'] = pending['created_at']
        # Store per-company client credentials so callback uses the same ones
        session['oauth_client_id'] = oauth_service.client_id
        session['oauth_client_secret'] = oauth_service.client_secret
        session['oauth_redirect_uri'] = oauth_service.redirect_uri

        logger.info(
            "Initiating OAuth flow",
            extra={'cif': clean_cif, 'state': state[:8] + '...'}
        )

        # Redirect to ANAF login page
        return redirect(auth_url)

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/oauth/callback', methods=['GET'])
@efactura_bp.route('/callback', methods=['GET'])  # Also handle /efactura/callback (ANAF registration)
@login_required
def oauth_callback():
    """
    Handle OAuth2 callback from ANAF.

    Query params (from ANAF):
        code: Authorization code
        state: State parameter for CSRF protection

    Exchanges code for tokens and stores them in database.
    """
    try:
        code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')
        error_description = request.args.get('error_description')

        # Check for error from ANAF
        if error:
            logger.error(
                f"OAuth error from ANAF: error={error!r} description={error_description!r}",
                extra={'error': error, 'description': error_description}
            )
            return render_template(
                'core/connectors/efactura/oauth_result.html',
                success=False,
                error=f"{error}: {error_description}" if error_description else error,
            )

        if not code or not state:
            return render_template(
                'core/connectors/efactura/oauth_result.html',
                success=False,
                error="Missing authorization code or state parameter",
            )

        # Validate state matches session
        session_state = session.get('oauth_state')
        session_cif = session.get('oauth_cif')

        if not session_state or state != session_state:
            logger.warning(
                "OAuth state mismatch",
                extra={'expected': session_state[:8] + '...' if session_state else 'None'}
            )
            return render_template(
                'core/connectors/efactura/oauth_result.html',
                success=False,
                error="Invalid state parameter. Please try again.",
            )

        # Get OAuth service — use per-company credentials from session if stored
        session_client_id = session.get('oauth_client_id')
        session_client_secret = session.get('oauth_client_secret')
        session_redirect_uri = session.get('oauth_redirect_uri')

        if session_client_id and session_client_secret:
            oauth_service = ANAFOAuthService(
                client_id=session_client_id,
                client_secret=session_client_secret,
                redirect_uri=session_redirect_uri,
            )
        else:
            oauth_service = get_oauth_service()

        # Restore pending auth data from session if needed
        pending = oauth_service.get_pending_auth(state)
        if not pending and session_cif:
            # Restore from session (in case of server restart or per-company service)
            oauth_service.store_pending_auth(state, {
                'code_verifier': session.get('oauth_code_verifier', ''),
                'cif': session_cif,
                'created_at': session.get('oauth_created_at', ''),
            })

        tokens = oauth_service.exchange_code_for_tokens(code, state)

        # Store tokens in database
        from ..repositories.oauth_repository import OAuthRepository

        token_data = tokens.to_dict()
        OAuthRepository().save_tokens(session_cif, token_data)

        # Auto-create company connection if it doesn't exist
        from ..repositories.company_repo import CompanyConnectionRepository
        company_repo = CompanyConnectionRepository()
        company_repo.ensure_connection_for_oauth(session_cif)

        # Clear session data
        session.pop('oauth_state', None)
        session.pop('oauth_cif', None)
        session.pop('oauth_code_verifier', None)
        session.pop('oauth_created_at', None)
        session.pop('oauth_client_id', None)
        session.pop('oauth_client_secret', None)
        session.pop('oauth_redirect_uri', None)

        logger.info(
            "OAuth flow completed successfully",
            extra={'cif': session_cif}
        )

        return render_template(
            'core/connectors/efactura/oauth_result.html',
            success=True,
            cif=session_cif,
            expires_at=tokens.expires_at.isoformat(),
        )

    except ValueError as e:
        logger.error(f"OAuth token exchange failed: {e}")
        return render_template(
            'core/connectors/efactura/oauth_result.html',
            success=False,
            error=str(e),
        )
    except Exception as e:
        logger.exception('OAuth callback error')
        return render_template(
            'core/connectors/efactura/oauth_result.html',
            success=False,
            error='An unexpected error occurred',
        )


@efactura_bp.route('/oauth/revoke', methods=['POST'])
@api_login_required
@efactura_access_required
def oauth_revoke():
    """
    Revoke OAuth tokens and disconnect from ANAF.

    Request body:
        cif: Company CIF (required)
    """
    try:
        data = request.get_json()
        cif = data.get('cif') if data else None

        if not cif:
            return jsonify({
                'success': False,
                'error': "Missing required field: cif",
            }), 400

        # Clean CIF
        clean_cif = cif.upper().replace('RO', '').strip()

        # Get current tokens to revoke
        from ..repositories.oauth_repository import OAuthRepository
        _oauth_repo = OAuthRepository()

        tokens = _oauth_repo.get_tokens(clean_cif)

        if tokens and tokens.get('refresh_token'):
            # Revoke token at ANAF
            oauth_service = get_oauth_service()
            oauth_service.revoke_token(tokens['refresh_token'])

        # Remove tokens via database function
        deleted = _oauth_repo.delete_tokens(clean_cif)

        if deleted:
            logger.info(
                "OAuth tokens revoked",
                extra={'cif': clean_cif}
            )
            return jsonify({
                'success': True,
                'message': 'Disconnected successfully',
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No active connection found',
            }), 404

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/oauth/status', methods=['GET'])
@api_login_required
@efactura_access_required
def oauth_status():
    """
    Get OAuth authentication status for a company.

    Query params:
        cif: Company CIF (required)

    Returns:
        authenticated: Whether valid tokens exist
        expires_at: Token expiration time (if authenticated)
        expires_in_seconds: Seconds until expiration
    """
    try:
        cif = request.args.get('cif')

        if not cif:
            return jsonify({
                'success': False,
                'error': "Missing required parameter: cif",
            }), 400

        # Clean CIF
        clean_cif = cif.upper().replace('RO', '').strip()

        from ..repositories.oauth_repository import OAuthRepository

        status = OAuthRepository().get_status(clean_cif)

        return jsonify({
            'success': True,
            'data': status,
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/oauth/refresh', methods=['POST'])
@api_login_required
@efactura_access_required
def oauth_refresh():
    """
    Manually refresh OAuth access token.

    Request body:
        cif: Company CIF (required)

    Normally tokens auto-refresh, but this endpoint allows manual refresh.
    """
    try:
        data = request.get_json()
        cif = data.get('cif') if data else None

        if not cif:
            return jsonify({
                'success': False,
                'error': "Missing required field: cif",
            }), 400

        # Clean CIF
        clean_cif = cif.upper().replace('RO', '').strip()

        from ..repositories.oauth_repository import OAuthRepository
        _oauth_repo = OAuthRepository()

        tokens = _oauth_repo.get_tokens(clean_cif)

        if not tokens or not tokens.get('refresh_token'):
            return jsonify({
                'success': False,
                'error': 'No active connection found. Please authenticate first.',
            }), 404

        # Refresh the token (use per-company credentials if configured)
        oauth_service = _get_oauth_service_for_cif(clean_cif)
        new_tokens = oauth_service.refresh_access_token(
            tokens['refresh_token'],
            clean_cif
        )

        # Save new tokens
        _oauth_repo.save_tokens(clean_cif, new_tokens.to_dict())

        logger.info(
            "OAuth tokens refreshed manually",
            extra={'cif': clean_cif}
        )

        return jsonify({
            'success': True,
            'message': 'Token refreshed successfully',
            'expires_at': new_tokens.expires_at.isoformat(),
        })

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e),
        }), 400
    except Exception as e:
        return safe_error_response(e)
