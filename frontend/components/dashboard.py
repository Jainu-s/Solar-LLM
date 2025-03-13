import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import datetime
from typing import Dict, Any, List, Optional

from frontend.utils.api import APIClient, APIError
from frontend.utils.session import get_user_setting
from frontend.enhanced_ui import custom_alert, card, custom_tabs

def dashboard_page(api_client: APIClient):
    """
    Main dashboard page component
    
    Args:
        api_client: API client instance
    """
    st.title("Solar LLM Dashboard")
    
    # Check if user is admin
    is_admin = st.session_state.user.get("role") == "admin"
    
    # Create tabs for different sections of the dashboard
    tab_names = ["Usage", "Files", "Performance"]
    
    if is_admin:
        tab_names.append("System Monitor")
        tab_names.append("User Analytics")
    
    tabs = st.tabs(tab_names)
    
    # Usage tab
    with tabs[0]:
        render_usage_tab(api_client)
    
    # Files tab
    with tabs[1]:
        render_files_tab(api_client)
    
    # Performance tab
    with tabs[2]:
        render_performance_tab(api_client)
    
    # Admin-only tabs
    if is_admin:
        # System Monitor tab
        with tabs[3]:
            render_system_tab(api_client)
        
        # User Analytics tab
        with tabs[4]:
            render_user_analytics_tab(api_client)

def render_usage_tab(api_client: APIClient):
    """Render the usage analytics tab"""
    st.header("Your Usage")
    
    try:
        # In a real app, get this data from the API
        # For now, we'll use mock data
        
        # Time period selector
        time_period = st.selectbox(
            "Time Period",
            options=["Last 7 days", "Last 30 days", "Last 3 months", "All time"],
            index=0
        )
        
        # Create metrics cards
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label="Total Queries",
                value="147",
                delta="23%",
                delta_color="normal",
                help="Total number of queries sent"
            )
        
        with col2:
            st.metric(
                label="Documents Analyzed",
                value="12",
                delta="5",
                delta_color="normal",
                help="Number of documents processed"
            )
        
        with col3:
            st.metric(
                label="Average Response Time",
                value="1.2s",
                delta="-0.3s",
                delta_color="inverse",
                help="Average time to generate responses"
            )
        
        with col4:
            st.metric(
                label="Feedback Score",
                value="4.7/5",
                delta="0.2",
                delta_color="normal",
                help="Average rating from your feedback"
            )
        
        # Create usage chart
        st.subheader("Usage Over Time")
        
        # Generate mock data
        dates = pd.date_range(end=datetime.datetime.now(), periods=30, freq='D')
        queries = np.random.randint(0, 15, size=30).cumsum()
        
        # Create a DataFrame
        df = pd.DataFrame({
            'date': dates,
            'queries': queries
        })
        
        # Create and display chart
        chart = alt.Chart(df).mark_line().encode(
            x='date:T',
            y='queries:Q',
            tooltip=['date:T', 'queries:Q']
        ).properties(
            width=700,
            height=400
        ).interactive()
        
        st.altair_chart(chart, use_container_width=True)
        
        # Recent queries
        st.subheader("Recent Queries")
        
        # Mock data for recent queries
        recent_queries = [
            {"query": "How do solar panels work?", "timestamp": "2 hours ago", "duration": "1.3s"},
            {"query": "What is the ROI for a 10kW system?", "timestamp": "Yesterday", "duration": "2.1s"},
            {"query": "Compare monocrystalline vs polycrystalline panels", "timestamp": "3 days ago", "duration": "0.9s"},
            {"query": "How many solar panels do I need for a 2000 sq ft home?", "timestamp": "5 days ago", "duration": "1.7s"},
        ]
        
        # Show queries in a table
        df_queries = pd.DataFrame(recent_queries)
        st.table(df_queries)
        
    except APIError as e:
        st.error(f"Failed to load usage data: {str(e)}")

def render_files_tab(api_client: APIClient):
    """Render the files management tab"""
    st.header("Your Documents")
    
    try:
        # Try to get files from API
        files = api_client.list_files()
        
        if not files:
            st.info("You haven't uploaded any documents yet.")
            
            # Show upload section
            st.subheader("Upload a Document")
            uploaded_file = st.file_uploader(
                "Upload a document to analyze with Solar LLM",
                type=["pdf", "txt", "docx", "csv", "json"]
            )
            
            if uploaded_file:
                # Handle file upload
                file_path = f"temp_{uploaded_file.name}"
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                # Form for additional metadata
                with st.form("file_metadata_form"):
                    title = st.text_input("Title", value=uploaded_file.name)
                    description = st.text_area("Description (optional)")
                    category = st.selectbox(
                        "Category",
                        options=["Solar Panel", "Inverter", "Battery", "System Design", "Other"]
                    )
                    add_to_index = st.checkbox("Add to knowledge base", value=True)
                    
                    submitted = st.form_submit_button("Upload")
                    
                    if submitted:
                        try:
                            # Upload file to server
                            file_response = api_client.upload_file(
                                file_path,
                                title=title,
                                description=description,
                                category=category,
                                add_to_index=add_to_index
                            )
                            
                            st.success(f"File uploaded: {title}")
                            st.rerun()
                            
                        except APIError as e:
                            st.error(f"Failed to upload file: {str(e)}")
            
            return
        
        # Display files in a more visual grid layout
        st.subheader("Document Library")
        
        # File type filter
        file_types = ["All"] + list(set(file.get("file_type", "").lstrip(".") for file in files))
        selected_type = st.selectbox("Filter by type", file_types)
        
        # Search box
        search_query = st.text_input("Search documents", placeholder="Enter keywords...")
        
        # Filter files by type and search query
        filtered_files = files
        if selected_type != "All":
            filtered_files = [f for f in filtered_files if f.get("file_type", "").lstrip(".") == selected_type]
        
        if search_query:
            search_query = search_query.lower()
            filtered_files = [
                f for f in filtered_files 
                if search_query in f.get("title", "").lower() 
                or search_query in f.get("description", "").lower()
            ]
        
        # Display files in a grid
        cols_per_row = 3
        for i in range(0, len(filtered_files), cols_per_row):
            cols = st.columns(cols_per_row)
            for j in range(cols_per_row):
                if i + j < len(filtered_files):
                    file = filtered_files[i + j]
                    with cols[j]:
                        # Create a card for each file
                        with st.expander(file.get("title", "Untitled"), expanded=True):
                            # Display file info
                            st.write(f"**Type:** {file.get('file_type', '').lstrip('.')}")
                            st.write(f"**Size:** {file.get('file_size', 0) / 1024:.1f} KB")
                            st.write(f"**Uploaded:** {file.get('upload_time', '')}")
                            
                            # Display description if available
                            if file.get("description"):
                                st.write(f"**Description:** {file.get('description')}")
                            
                            # Actions
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                if st.button("Download", key=f"download_{file.get('id')}"):
                                    try:
                                        # Download file
                                        api_client.get_file(file.get("id"), download=True)
                                        st.success("Download started")
                                    except APIError as e:
                                        st.error(f"Failed to download: {str(e)}")
                            
                            with col2:
                                if st.button("Delete", key=f"delete_{file.get('id')}"):
                                    try:
                                        # Delete file
                                        api_client.delete_file(file.get("id"))
                                        st.success("File deleted")
                                        st.rerun()
                                    except APIError as e:
                                        st.error(f"Failed to delete: {str(e)}")
        
        # Upload new document button
        st.subheader("Upload a New Document")
        uploaded_file = st.file_uploader(
            "Upload a document to analyze with Solar LLM",
            type=["pdf", "txt", "docx", "csv", "json"],
            key="dashboard_uploader"
        )
        
        if uploaded_file:
            # Handle file upload
            file_path = f"temp_{uploaded_file.name}"
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            # Form for additional metadata
            with st.form("file_metadata_form"):
                title = st.text_input("Title", value=uploaded_file.name)
                description = st.text_area("Description (optional)")
                category = st.selectbox(
                    "Category",
                    options=["Solar Panel", "Inverter", "Battery", "System Design", "Other"]
                )
                add_to_index = st.checkbox("Add to knowledge base", value=True)
                
                submitted = st.form_submit_button("Upload")
                
                if submitted:
                    try:
                        # Upload file to server
                        file_response = api_client.upload_file(
                            file_path,
                            title=title,
                            description=description,
                            category=category,
                            add_to_index=add_to_index
                        )
                        
                        st.success(f"File uploaded: {title}")
                        st.rerun()
                        
                    except APIError as e:
                        st.error(f"Failed to upload file: {str(e)}")
        
    except APIError as e:
        st.error(f"Failed to load documents: {str(e)}")

def render_performance_tab(api_client: APIClient):
    """Render the performance analytics tab"""
    st.header("Performance Metrics")
    
    try:
        # Time period selector
        time_period = st.selectbox(
            "Time Period",
            options=["Last 7 days", "Last 30 days", "Last 3 months"],
            index=0,
            key="perf_time_period"
        )
        
        # Mock performance data
        days = 30 if "30" in time_period else 7 if "7" in time_period else 90
        dates = pd.date_range(end=datetime.datetime.now(), periods=days, freq='D')
        
        # Generate some random performance data
        response_times = 0.5 + np.random.rand(days) * 2  # Response times between 0.5 and 2.5 seconds
        token_counts = np.random.randint(100, 800, size=days)  # Token counts between 100 and 800
        
        # Create DataFrame
        df_perf = pd.DataFrame({
            'date': dates,
            'response_time': response_times,
            'tokens': token_counts
        })
        
        # Display metrics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                label="Average Response Time",
                value=f"{df_perf['response_time'].mean():.2f}s",
                delta=f"{df_perf['response_time'].iloc[-1] - df_perf['response_time'].iloc[0]:.2f}s",
                delta_color="inverse"
            )
        
        with col2:
            st.metric(
                label="Average Tokens per Query",
                value=f"{df_perf['tokens'].mean():.0f}",
                delta=f"{df_perf['tokens'].iloc[-1] - df_perf['tokens'].iloc[0]:.0f}"
            )
        
        with col3:
            st.metric(
                label="Query Success Rate",
                value="98.7%",
                delta="0.5%"
            )
        
        # Response time chart
        st.subheader("Response Time Trend")
        
        chart_time = alt.Chart(df_perf).mark_line().encode(
            x='date:T',
            y=alt.Y('response_time:Q', title='Response Time (seconds)'),
            tooltip=['date:T', 'response_time:Q']
        ).properties(
            width=700,
            height=300
        ).interactive()
        
        st.altair_chart(chart_time, use_container_width=True)
        
        # Token usage chart
        st.subheader("Token Usage Trend")
        
        chart_tokens = alt.Chart(df_perf).mark_bar().encode(
            x='date:T',
            y=alt.Y('tokens:Q', title='Token Count'),
            tooltip=['date:T', 'tokens:Q']
        ).properties(
            width=700,
            height=300
        ).interactive()
        
        st.altair_chart(chart_tokens, use_container_width=True)
        
        # Model comparison
        st.subheader("Model Performance Comparison")
        
        # Mock data for model comparison
        models = ["Default", "GPT-3.5", "GPT-4", "Claude"]
        response_times_by_model = [1.2, 1.5, 2.3, 1.8]
        accuracy_by_model = [0.92, 0.94, 0.98, 0.96]
        
        # Create DataFrame
        df_models = pd.DataFrame({
            'model': models,
            'response_time': response_times_by_model,
            'accuracy': accuracy_by_model
        })
        
        # Create two-column view
        col1, col2 = st.columns(2)
        
        with col1:
            # Response time by model
            chart_model_time = alt.Chart(df_models).mark_bar().encode(
                x=alt.X('model:N', title='Model'),
                y=alt.Y('response_time:Q', title='Avg. Response Time (s)'),
                color='model:N',
                tooltip=['model:N', 'response_time:Q']
            ).properties(
                width=300,
                height=300,
                title='Response Time by Model'
            ).interactive()
            
            st.altair_chart(chart_model_time, use_container_width=True)
        
        with col2:
            # Accuracy by model
            chart_model_acc = alt.Chart(df_models).mark_bar().encode(
                x=alt.X('model:N', title='Model'),
                y=alt.Y('accuracy:Q', title='Accuracy', scale=alt.Scale(domain=[0.85, 1])),
                color='model:N',
                tooltip=['model:N', 'accuracy:Q']
            ).properties(
                width=300,
                height=300,
                title='Accuracy by Model'
            ).interactive()
            
            st.altair_chart(chart_model_acc, use_container_width=True)
        
    except APIError as e:
        st.error(f"Failed to load performance data: {str(e)}")

def render_system_tab(api_client: APIClient):
    """Render the system monitoring tab (admin only)"""
    st.header("System Monitor")
    
    try:
        # Get system status
        system_status = api_client.get_system_status()
        
        if system_status.get("status") == "unauthorized":
            st.error("You don't have permission to view system status.")
            return
        
        # Display status badges
        status_color = {
            "ok": "success",
            "degraded": "warning",
            "critical": "error"
        }.get(system_status.get("status", ""), "info")
        
        st.markdown(f"""
        <div style='display: inline-block; padding: 0.5em 1em; background-color: var(--{status_color}-50); 
                    color: var(--{status_color}-700); border-radius: 0.5em; font-weight: bold;'>
            System Status: {system_status.get("status", "Unknown").upper()}
        </div>
        """, unsafe_allow_html=True)
        
        # Resource metrics
        st.subheader("Resource Utilization")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            cpu_percent = system_status.get("resources", {}).get("cpu_percent", 0)
            st.progress(cpu_percent / 100, text=f"CPU: {cpu_percent}%")
        
        with col2:
            memory_percent = system_status.get("resources", {}).get("memory_percent", 0)
            st.progress(memory_percent / 100, text=f"Memory: {memory_percent}%")
        
        with col3:
            disk_percent = system_status.get("resources", {}).get("disk_percent", 0)
            st.progress(disk_percent / 100, text=f"Disk: {disk_percent}%")
        
        # Component status
        st.subheader("Component Status")
        
        components = system_status.get("components", {})
        
        for component_name, component_data in components.items():
            component_status = component_data.get("status", "unknown")
            status_emoji = {
                "ok": "✅",
                "degraded": "⚠️",
                "error": "❌",
                "unknown": "❓"
            }.get(component_status, "❓")
            
            st.markdown(f"**{component_name.title()}**: {status_emoji} {component_status.upper()}")
            
            # Display additional component details
            with st.expander(f"{component_name.title()} Details"):
                # Remove status field from display
                component_details = {k: v for k, v in component_data.items() if k != "status"}
                st.json(component_details)
        
        # System actions
        st.subheader("System Actions")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("Optimize System", use_container_width=True):
                try:
                    # Call optimize endpoint
                    optimization_result = {"status": "completed", "message": "System optimization completed"}
                    st.success(f"System optimization completed")
                except APIError as e:
                    st.error(f"Failed to optimize system: {str(e)}")
        
        with col2:
            if st.button("Clear Caches", use_container_width=True):
                try:
                    # Call cache clear endpoint
                    cache_result = {"items_cleared": 145}
                    st.success(f"Cleared {cache_result.get('items_cleared', 0)} cached items")
                except APIError as e:
                    st.error(f"Failed to clear caches: {str(e)}")
        
        # Recent errors
        st.subheader("Recent Errors")
        
        # Mock error data
        error_data = [
            {"timestamp": "2023-08-10 14:23:45", "error": "Database connection timeout", "count": 3},
            {"timestamp": "2023-08-10 12:15:32", "error": "API rate limit exceeded", "count": 1},
            {"timestamp": "2023-08-09 23:45:18", "error": "Document processing failed", "count": 2}
        ]
        
        if error_data:
            df_errors = pd.DataFrame(error_data)
            st.table(df_errors)
        else:
            st.info("No recent errors")
        
    except APIError as e:
        st.error(f"Failed to load system status: {str(e)}")

def render_user_analytics_tab(api_client: APIClient):
    """Render the user analytics tab (admin only)"""
    st.header("User Analytics")
    
    try:
        # Get analytics data
        analytics_data = api_client.get_analytics_dashboard()
        
        if analytics_data.get("status") == "unauthorized":
            st.error("You don't have permission to view analytics data.")
            return
        
        # Mock user analytics data
        daily_stats = {
            "days": ["2023-08-05", "2023-08-06", "2023-08-07", "2023-08-08", "2023-08-09", "2023-08-10", "2023-08-11"],
            "queries": [145, 152, 137, 168, 192, 178, 203],
            "errors": [3, 5, 2, 4, 7, 3, 6],
            "users": [12, 15, 14, 18, 20, 19, 22]
        }
        
        # Create DataFrame
        df_stats = pd.DataFrame({
            'date': daily_stats["days"],
            'queries': daily_stats["queries"],
            'errors': daily_stats["errors"],
            'users': daily_stats["users"]
        })
        
        # Display metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label="Total Users",
                value="48",
                delta="5",
                help="Total number of users in the system"
            )
        
        with col2:
            st.metric(
                label="Active Users (24h)",
                value="22",
                delta="2",
                help="Users active in the last 24 hours"
            )
        
        with col3:
            st.metric(
                label="Total Queries",
                value=str(sum(daily_stats["queries"])),
                delta="15%",
                help="Total queries across all users"
            )
        
        with col4:
            st.metric(
                label="Error Rate",
                value="3.2%",
                delta="-0.5%",
                delta_color="inverse",
                help="Percentage of queries resulting in errors"
            )
        
        # User activity chart
        st.subheader("User Activity")
        
        chart_users = alt.Chart(df_stats).mark_line().encode(
            x='date:T',
            y='users:Q',
            tooltip=['date:T', 'users:Q']
        ).properties(
            width=700,
            height=300,
            title='Daily Active Users'
        ).interactive()
        
        st.altair_chart(chart_users, use_container_width=True)
        
        # Queries vs errors chart
        st.subheader("Queries and Errors")
        
        # Prepare data for multi-line chart
        source = pd.DataFrame({
            'date': df_stats['date'].tolist() * 2,
            'metric': ['Queries'] * len(df_stats) + ['Errors'] * len(df_stats),
            'value': df_stats['queries'].tolist() + df_stats['errors'].tolist()
        })
        
        chart_combined = alt.Chart(source).mark_line().encode(
            x='date:T',
            y='value:Q',
            color='metric:N',
            tooltip=['date:T', 'metric:N', 'value:Q']
        ).properties(
            width=700,
            height=300,
            title='Queries vs Errors'
        ).interactive()
        
        st.altair_chart(chart_combined, use_container_width=True)
        
        # Top queries
        st.subheader("Top Queries")
        
        # Mock top query data
        top_queries = [
            {"query": "How do solar panels work?", "count": 78, "last_seen": "2023-08-11T14:23:45"},
            {"query": "What is the ROI for a 10kW system?", "count": 65, "last_seen": "2023-08-11T12:15:32"},
            {"query": "Compare monocrystalline vs polycrystalline panels", "count": 52, "last_seen": "2023-08-10T23:45:18"},
            {"query": "How many solar panels do I need for a 2000 sq ft home?", "count": 43, "last_seen": "2023-08-11T09:12:37"},
            {"query": "Cost of a battery backup system", "count": 37, "last_seen": "2023-08-11T11:05:22"},
        ]
        
        # Show queries in a table
        df_top_queries = pd.DataFrame(top_queries)
        st.table(df_top_queries)
        
        # User engagement metrics
        st.subheader("User Engagement")
        
        # Mock user engagement data
        user_engagement = {
            "average_session_duration": "12m 34s",
            "average_queries_per_session": 5.3,
            "returning_user_rate": "68%",
            "satisfaction_score": 4.7
        }
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label="Avg. Session",
                value=user_engagement["average_session_duration"]
            )
        
        with col2:
            st.metric(
                label="Queries/Session",
                value=user_engagement["average_queries_per_session"]
            )
        
        with col3:
            st.metric(
                label="Return Rate",
                value=user_engagement["returning_user_rate"]
            )
        
        with col4:
            st.metric(
                label="Satisfaction",
                value=user_engagement["satisfaction_score"]
            )
        
        # Export options
        st.subheader("Export Analytics")
        
        with st.form("export_form"):
            export_start_date = st.date_input("Start Date", value=datetime.datetime.now() - datetime.timedelta(days=7))
            export_end_date = st.date_input("End Date", value=datetime.datetime.now())
            export_format = st.selectbox("Format", options=["JSON", "CSV", "Excel"])
            
            export_submitted = st.form_submit_button("Export Data")
            
            if export_submitted:
                if export_start_date > export_end_date:
                    st.error("Start date must be before end date")
                else:
                    try:
                        # In a real app, call the export API
                        st.success(f"Analytics exported in {export_format} format")
                        st.download_button(
                            label=f"Download {export_format} File",
                            data=b"Mock data export",
                            file_name=f"analytics_export_{export_start_date}_{export_end_date}.{export_format.lower()}",
                            mime=f"application/{export_format.lower()}"
                        )
                    except APIError as e:
                        st.error(f"Failed to export data: {str(e)}")
        
    except APIError as e:
        st.error(f"Failed to load analytics data: {str(e)}")