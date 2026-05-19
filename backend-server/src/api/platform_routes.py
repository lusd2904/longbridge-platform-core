from flask import Blueprint, jsonify, request

from api.auth_routes import admin_required, login_required
from core.account.DataPersistence import get_persistence_manager
from core.analysis.DailyMarketScanService import DailyMarketScanService
from core.analysis.DailySymbolTrendScanScheduler import daily_symbol_trend_scan_scheduler
from core.analysis.DailySymbolTrendScanService import DailySymbolTrendScanService
from core.analysis.FinanceBriefingService import FinanceBriefingService
from core.analysis.IndicatorSnapshotService import IndicatorSnapshotService
from core.analysis.MarketHistoryBootstrapService import MarketHistoryBootstrapService
from core.analysis.MarketInsightService import MarketInsightService
from core.analysis.RecommendationService import RecommendationService
from core.analysis.HistoricalMarketDataService import HistoricalMarketDataService
from core.analysis.MarketHistoryBackfillScheduler import market_history_backfill_scheduler
from core.platform.PlatformAuditService import PlatformAuditService
from core.platform.PlatformAccessService import PlatformAccessService
from core.platform.ServiceGovernanceService import ServiceGovernanceService
from core.platform.SystemSettingsService import SystemSettingsService
from core.platform.SystemTaskService import SystemTaskService
from core.platform.TradeAuditService import TradeAuditService
from utils.DbUtil import DbUtil

platform_bp = Blueprint('platform', __name__)


@platform_bp.route('/api/platform/bootstrap', methods=['GET'])
@login_required
def get_platform_bootstrap():
    try:
        payload = PlatformAccessService.build_user_bootstrap(request.user_id)
        if payload.get('access', {}).get('canManageTasks'):
            payload['tasks'] = SystemTaskService.list_policies()
        return jsonify({'success': True, 'data': payload})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@platform_bp.route('/api/platform/roles', methods=['GET'])
@login_required
@admin_required
def get_platform_roles():
    try:
        return jsonify({'success': True, 'data': PlatformAccessService.list_roles()})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@platform_bp.route('/api/platform/menus', methods=['GET'])
@login_required
@admin_required
def get_platform_menus():
    try:
        return jsonify({'success': True, 'data': PlatformAccessService.list_menus()})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@platform_bp.route('/api/platform/roles', methods=['POST'])
@login_required
@admin_required
def create_platform_role():
    try:
        payload = request.get_json(silent=True) or {}
        role = PlatformAccessService.upsert_role(
            role_code=payload.get('roleCode') or payload.get('role_code'),
            role_name=payload.get('roleName') or payload.get('role_name'),
            description=payload.get('description') or '',
            priority=int(payload.get('priority') or 0),
            menu_codes=payload.get('menuCodes') or payload.get('menu_codes') or [],
            extra_capabilities=payload.get('extraCapabilities') or payload.get('extra_capabilities'),
            is_system=bool(payload.get('isSystem', False))
        )
        PlatformAuditService.log(
            user_id=request.user_id,
            username=getattr(request, 'username', None),
            module='roles',
            operation='create-role',
            description=f"创建角色 {role.get('roleCode') or payload.get('roleCode')}"
        )
        return jsonify({'success': True, 'data': role, 'message': '角色已创建'})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@platform_bp.route('/api/platform/roles/<role_code>', methods=['PUT'])
@login_required
@admin_required
def update_platform_role(role_code):
    try:
        payload = request.get_json(silent=True) or {}
        role = PlatformAccessService.upsert_role(
            role_code=role_code,
            role_name=payload.get('roleName') or payload.get('role_name'),
            description=payload.get('description') or '',
            priority=int(payload.get('priority') or 0),
            menu_codes=payload.get('menuCodes') or payload.get('menu_codes') or [],
            extra_capabilities=payload.get('extraCapabilities') or payload.get('extra_capabilities'),
            is_system=payload.get('isSystem')
        )
        PlatformAuditService.log(
            user_id=request.user_id,
            username=getattr(request, 'username', None),
            module='roles',
            operation='update-role',
            description=f"更新角色 {role_code}"
        )
        return jsonify({'success': True, 'data': role, 'message': '角色权限已更新'})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@platform_bp.route('/api/platform/tasks', methods=['GET'])
@login_required
@admin_required
def get_platform_tasks():
    try:
        return jsonify({'success': True, 'data': SystemTaskService.list_policies()})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@platform_bp.route('/api/platform/service-governance', methods=['GET'])
@login_required
@admin_required
def get_service_governance():
    try:
        return jsonify({'success': True, 'data': ServiceGovernanceService.get_snapshot()})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@platform_bp.route('/api/platform/trade-audits', methods=['GET'])
@login_required
def get_trade_audits():
    try:
        limit = max(20, min(int(request.args.get('limit', 120) or 120), 300))
        scope = str(request.args.get('scope', '') or '').strip().lower()
        target_user_id = None if request.role == 'admin' and scope == 'all' else request.user_id
        return jsonify({'success': True, 'data': TradeAuditService.list_recent(limit=limit, user_id=target_user_id)})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@platform_bp.route('/api/platform/tasks/<task_key>', methods=['PUT'])
@login_required
@admin_required
def update_platform_task(task_key):
    try:
        payload = request.get_json(silent=True) or {}
        policy = SystemTaskService.update_policy(task_key, payload)
        PlatformAuditService.log(
            user_id=request.user_id,
            username=getattr(request, 'username', None),
            module='tasks',
            operation='update-policy',
            description=f"更新任务策略 {task_key}"
        )
        return jsonify({'success': True, 'data': policy, 'message': '任务策略已更新'})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@platform_bp.route('/api/platform/tasks/<task_key>/run', methods=['POST'])
@login_required
@admin_required
def run_platform_task(task_key):
    try:
        if task_key == 'finance_briefing_refresh':
            result = FinanceBriefingService.refresh_all_markets(user_id=request.user_id)
        elif task_key == 'daily_market_ai_scan':
            result = DailyMarketScanService.refresh_all_markets(user_id=request.user_id)
        elif task_key == 'daily_symbol_trend_ai_scan':
            result = daily_symbol_trend_scan_scheduler.run_once()
        elif task_key == 'market_insight_refresh':
            result = MarketInsightService.refresh_all_markets(user_id=request.user_id, source='manual')
        elif task_key == 'recommendation_refresh':
            RecommendationService.refresh_all_profiles(user_id=request.user_id)
            result = RecommendationService.get_latest(user_id=request.user_id)
        elif task_key == 'symbol_indicator_daily_refresh':
            batch_size = SystemTaskService.get_batch_size(task_key, 1500)
            policy = SystemTaskService.get_policy(task_key)
            cursor = int((policy.get('settings') or {}).get('cursor') or 0)
            result = IndicatorSnapshotService.refresh_universe(batch_size=batch_size, cursor=cursor)
        elif task_key == 'market_history_universe_backfill':
            result = market_history_backfill_scheduler.run_once()
        elif task_key == 'bootstrap_market_history_2024':
            result = MarketHistoryBootstrapService.run_once(user_id=request.user_id, batch_size=SystemTaskService.get_batch_size(task_key, 160))
        else:
            return jsonify({'success': False, 'error': '暂不支持的任务'}), 400

        PlatformAuditService.log(
            user_id=request.user_id,
            username=getattr(request, 'username', None),
            module='tasks',
            operation='run-task',
            description=f"手动执行任务 {task_key}"
        )
        return jsonify({'success': True, 'data': result, 'message': '任务已执行'})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@platform_bp.route('/api/platform/finance-briefings', methods=['GET'])
@login_required
def get_finance_briefings():
    try:
        limit = int(request.args.get('limit', 18))
        market = str(request.args.get('market', '') or '').strip().upper()
        items = FinanceBriefingService.get_latest(limit=limit, market=market or None)
        if str(request.args.get('refresh') or '').strip().lower() in {'1', 'true', 'yes', 'on'}:
            FinanceBriefingService.refresh_all_markets(user_id=request.user_id)
            items = FinanceBriefingService.get_latest(limit=limit, market=market or None)
        return jsonify({'success': True, 'data': items})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@platform_bp.route('/api/platform/market-scans', methods=['GET'])
@login_required
def get_market_scans():
    try:
        scans = DailyMarketScanService.get_latest_scans()
        if not scans:
            try:
                DailyMarketScanService.refresh_all_markets(user_id=request.user_id)
            except Exception:
                pass
            scans = DailyMarketScanService.get_latest_scans()
        return jsonify({'success': True, 'data': scans})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@platform_bp.route('/api/platform/symbols/<path:symbol>/overview', methods=['GET'])
@login_required
def get_symbol_overview(symbol):
    try:
        normalized_symbol = HistoricalMarketDataService.normalize_symbol(symbol)
        overview = IndicatorSnapshotService.get_symbol_overview(normalized_symbol, user_id=request.user_id)
        history = HistoricalMarketDataService.get_history(normalized_symbol, timeframe='daily', limit=120, user_id=request.user_id)
        persistence = get_persistence_manager()
        latest_ai = persistence.get_latest_ai_analysis(normalized_symbol, user_id=request.user_id)
        latest_ai_payload = latest_ai.to_dict() if latest_ai else None
        market_insights = {item['market']: item for item in MarketInsightService.get_latest_snapshots(user_id=request.user_id)}
        market_scans = {item['market']: item for item in DailyMarketScanService.get_latest_scans()}
        latest_trend_scan = DailySymbolTrendScanService.get_latest_for_symbol(normalized_symbol)

        return jsonify({
            'success': True,
            'data': {
                **overview,
                'history': history,
                'latestAiAnalysis': latest_ai_payload,
                'latestTrendScan': latest_trend_scan,
                'marketInsight': market_insights.get(overview.get('market')),
                'marketScan': market_scans.get(overview.get('market'))
            }
        })
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@platform_bp.route('/api/platform/system-settings', methods=['GET'])
@login_required
@admin_required
def get_system_settings():
    try:
        return jsonify({'success': True, 'data': SystemSettingsService.get_all()})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@platform_bp.route('/api/platform/system-settings', methods=['PUT'])
@login_required
@admin_required
def update_system_settings():
    try:
        payload = request.get_json(silent=True) or {}
        settings_payload = payload.get('settings') if isinstance(payload.get('settings'), dict) else payload
        updated = SystemSettingsService.update_many(settings_payload, user_id=request.user_id)
        PlatformAuditService.log(
            user_id=request.user_id,
            username=getattr(request, 'username', None),
            module='settings',
            operation='update-system-settings',
            description='更新系统基础设置'
        )
        return jsonify({'success': True, 'data': updated, 'message': '系统设置已更新'})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@platform_bp.route('/api/platform/system-logs', methods=['GET'])
@login_required
@admin_required
def get_system_logs():
    try:
        limit = max(20, min(int(request.args.get('limit', 120) or 120), 300))
        level = str(request.args.get('level', '') or '').strip().lower()

        audit_items = PlatformAuditService.list_recent(limit=limit, level=level)

        system_rows = DbUtil.fetch_all(
            """
            SELECT id, log_content, created_at
            FROM system_logs
            ORDER BY id DESC
            LIMIT %s
            """,
            (limit,)
        ) or []
        system_items = [
            {
                'id': int(row.get('id') or 0),
                'time': row.get('created_at').strftime('%Y-%m-%d %H:%M:%S') if row.get('created_at') else None,
                'level': 'error' if '失败' in (row.get('log_content') or '') or 'ERROR' in (row.get('log_content') or '') else 'info',
                'module': 'system',
                'operation': 'runtime',
                'message': row.get('log_content') or ''
            }
            for row in system_rows
        ]

        login_rows = DbUtil.fetch_all(
            """
            SELECT id, username, login_time, login_status, fail_reason
            FROM login_logs
            ORDER BY id DESC
            LIMIT %s
            """,
            (limit,)
        ) or []
        login_items = [
            {
                'id': int(row.get('id') or 0),
                'time': row.get('login_time').strftime('%Y-%m-%d %H:%M:%S') if row.get('login_time') else None,
                'level': 'warning' if row.get('login_status') == 'failed' else 'info',
                'module': 'auth',
                'operation': 'login',
                'message': f"{row.get('username') or 'unknown'} 登录{'失败' if row.get('login_status') == 'failed' else '成功'}"
                           + (f"：{row.get('fail_reason')}" if row.get('fail_reason') else '')
            }
            for row in login_rows
        ]

        task_rows = DbUtil.fetch_all(
            """
            SELECT job_name, status, message, COALESCE(last_run_at, updated_at) AS event_time
            FROM scheduled_jobs
            ORDER BY COALESCE(last_run_at, updated_at) DESC
            LIMIT %s
            """,
            (limit,)
        ) or []
        task_items = [
            {
                'id': index + 1,
                'time': row.get('event_time').strftime('%Y-%m-%d %H:%M:%S') if row.get('event_time') else None,
                'level': 'error' if row.get('status') == 'failed' else 'warning' if row.get('status') == 'running' else 'info',
                'module': 'scheduler',
                'operation': row.get('job_name') or 'task',
                'message': row.get('message') or ''
            }
            for index, row in enumerate(task_rows)
        ]

        items = audit_items + system_items + login_items + task_items
        if level and level != 'all':
            items = [item for item in items if (item.get('level') or 'info') == level]
        items.sort(key=lambda item: item.get('time') or '', reverse=True)
        return jsonify({'success': True, 'data': items[:limit]})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500
