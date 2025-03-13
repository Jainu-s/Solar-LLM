# Import all component modules for easier access
from frontend.components.auth import (
    login_page,
    register_page,
    forgot_password_page,
    reset_password_page,
    auth_required,
    user_profile_section,
    change_password_section,
    active_sessions_section
)

from frontend.components.chat import (
    chat_page, 
    handle_message_submit,
    handle_suggestion_click,
    process_chat_message,
    render_chat_interface
)

from frontend.components.dashboard import (
    dashboard_page,
    render_usage_tab,
    render_files_tab,
    render_performance_tab,
    render_system_tab,
    render_user_analytics_tab
)

from frontend.components.settings import (
    settings_page,
    render_application_settings,
    render_chat_settings,
    render_profile_settings,
    render_appearance_settings,
    render_advanced_settings
)

from frontend.components.visualizations import (
    visualization_interface,
    visualize_data,
    process_data,
    auto_select_viz_type,
    create_bar_chart,
    create_line_chart,
    create_scatter_plot,
    create_pie_chart,
    create_histogram,
    create_heatmap,
    create_box_plot,
    create_area_chart,
    create_table,
    create_map
)