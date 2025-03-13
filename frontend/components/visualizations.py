import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go
from typing import Dict, Any, List, Optional, Union, Tuple
import json
import base64
import io

from frontend.utils.api import APIClient, APIError
from frontend.enhanced_ui import custom_alert

def visualize_data(
    data: Union[pd.DataFrame, List[Dict[str, Any]], str],
    viz_type: str = "auto",
    title: str = "Data Visualization",
    **kwargs
) -> None:
    """
    Create and display a visualization for the provided data
    
    Args:
        data: DataFrame, list of dictionaries, or CSV/JSON string
        viz_type: Type of visualization (bar, line, scatter, pie, etc.)
        title: Title for the visualization
        **kwargs: Additional visualization options
    """
    # Process data into a DataFrame
    df = process_data(data)
    
    if df is None or df.empty:
        st.error("No valid data to visualize")
        return
    
    # Auto-detect visualization type if set to auto
    if viz_type == "auto":
        viz_type = auto_select_viz_type(df)
        st.info(f"Auto-selected visualization type: {viz_type.title()}")
    
    # Create visualization based on type
    if viz_type == "bar":
        create_bar_chart(df, title, **kwargs)
    elif viz_type == "line":
        create_line_chart(df, title, **kwargs)
    elif viz_type == "scatter":
        create_scatter_plot(df, title, **kwargs)
    elif viz_type == "pie":
        create_pie_chart(df, title, **kwargs)
    elif viz_type == "histogram":
        create_histogram(df, title, **kwargs)
    elif viz_type == "heatmap":
        create_heatmap(df, title, **kwargs)
    elif viz_type == "box":
        create_box_plot(df, title, **kwargs)
    elif viz_type == "area":
        create_area_chart(df, title, **kwargs)
    elif viz_type == "table":
        create_table(df, title, **kwargs)
    elif viz_type == "map":
        create_map(df, title, **kwargs)
    else:
        st.error(f"Unsupported visualization type: {viz_type}")
        # Fallback to table view
        create_table(df, f"{title} (Table View)", **kwargs)

def process_data(data: Union[pd.DataFrame, List[Dict[str, Any]], str]) -> Optional[pd.DataFrame]:
    """
    Process input data into a pandas DataFrame
    
    Args:
        data: Input data in various formats
    
    Returns:
        Processed pandas DataFrame or None if invalid
    """
    try:
        if isinstance(data, pd.DataFrame):
            return data
        
        if isinstance(data, list) and all(isinstance(item, dict) for item in data):
            return pd.DataFrame(data)
        
        if isinstance(data, str):
            # Check if it's a CSV string
            if "," in data and "\n" in data:
                return pd.read_csv(io.StringIO(data))
            
            # Check if it's a JSON string
            try:
                json_data = json.loads(data)
                if isinstance(json_data, list) and all(isinstance(item, dict) for item in json_data):
                    return pd.DataFrame(json_data)
                elif isinstance(json_data, dict):
                    # Handle dictionary with lists as values
                    if all(isinstance(v, list) for v in json_data.values()):
                        return pd.DataFrame(json_data)
                    # Handle dictionary with simple values
                    else:
                        return pd.DataFrame([json_data])
            except:
                pass
        
        # If we get here, the format is unsupported
        st.error("Unsupported data format. Please provide a DataFrame, list of dictionaries, or CSV/JSON string.")
        return None
    
    except Exception as e:
        st.error(f"Error processing data: {str(e)}")
        return None

def auto_select_viz_type(df: pd.DataFrame) -> str:
    """
    Automatically select the best visualization type based on the data
    
    Args:
        df: DataFrame to visualize
    
    Returns:
        Recommended visualization type
    """
    # Get column types
    num_columns = df.select_dtypes(include=["int64", "float64"]).columns
    cat_columns = df.select_dtypes(include=["object", "category", "bool"]).columns
    date_columns = df.select_dtypes(include=["datetime64"]).columns
    
    # Get counts
    num_count = len(num_columns)
    cat_count = len(cat_columns)
    date_count = len(date_columns)
    
    # Check if we have coordinates for a map
    has_lat_lon = (
        ("lat" in df.columns.str.lower() or "latitude" in df.columns.str.lower()) and
        ("lon" in df.columns.str.lower() or "lng" in df.columns.str.lower() or "longitude" in df.columns.str.lower())
    )
    
    # Simple decision tree for visualization type
    
    # If data has coordinates, recommend a map
    if has_lat_lon:
        return "map"
    
    # If data has dates and numbers, recommend a line chart
    if date_count > 0 and num_count > 0:
        return "line"
    
    # If data has only a few categories and a numeric column, recommend a bar chart
    if cat_count == 1 and num_count >= 1 and df[cat_columns[0]].nunique() <= 20:
        return "bar"
    
    # If data has exactly two numeric columns, recommend a scatter plot
    if num_count == 2 and cat_count <= 1:
        return "scatter"
    
    # If data has a single category column with few unique values and a numeric column,
    # recommend a pie chart
    if cat_count == 1 and num_count == 1 and df[cat_columns[0]].nunique() <= 10:
        return "pie"
    
    # If data has exactly one numeric column, recommend a histogram
    if num_count == 1 and cat_count == 0:
        return "histogram"
    
    # If data has two category columns and a numeric column, recommend a heatmap
    if cat_count >= 2 and num_count >= 1:
        return "heatmap"
    
    # If data has multiple numeric columns, recommend a line chart
    if num_count > 1:
        return "line"
    
    # Default to table view if no better recommendation
    return "table"

def create_bar_chart(
    df: pd.DataFrame, 
    title: str = "Bar Chart", 
    x: Optional[str] = None,
    y: Optional[str] = None,
    color: Optional[str] = None,
    **kwargs
) -> None:
    """Create and display a bar chart"""
    # Auto-select columns if not provided
    if x is None or y is None:
        # Identify categorical and numerical columns
        num_columns = df.select_dtypes(include=["int64", "float64"]).columns
        cat_columns = df.select_dtypes(include=["object", "category", "bool"]).columns
        
        if x is None and len(cat_columns) > 0:
            x = cat_columns[0]
        elif x is None and len(num_columns) > 0:
            # If no categorical columns, use the first numeric column
            x = num_columns[0]
        
        if y is None and len(num_columns) > 0:
            # Find a numeric column that's not x
            for col in num_columns:
                if col != x:
                    y = col
                    break
            
            # If we couldn't find a different column, use the first numeric column
            if y is None and len(num_columns) > 0:
                y = num_columns[0]
    
    # If we still don't have x or y, use the first two columns
    if x is None and len(df.columns) > 0:
        x = df.columns[0]
    if y is None and len(df.columns) > 1:
        y = df.columns[1]
    elif y is None and len(df.columns) > 0:
        y = df.columns[0]
    
    # Create chart with Plotly
    try:
        fig = px.bar(
            df, 
            x=x, 
            y=y, 
            color=color,
            title=title,
            labels={col: col.replace("_", " ").title() for col in df.columns},
            height=kwargs.get("height", 500),
            template="plotly_white"
        )
        
        # Update layout
        fig.update_layout(
            xaxis_title=kwargs.get("x_label", x),
            yaxis_title=kwargs.get("y_label", y),
            legend_title=kwargs.get("legend_title", color),
            margin=dict(l=40, r=40, t=50, b=40)
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.error(f"Error creating bar chart: {str(e)}")
        # Fallback to a simpler implementation using Altair
        try:
            chart = alt.Chart(df).mark_bar().encode(
                x=x,
                y=y,
                color=color
            ).properties(
                title=title
            )
            
            st.altair_chart(chart, use_container_width=True)
        except:
            st.error("Could not create visualization with the selected columns")
            # Show data as table
            st.write(df)

def create_line_chart(
    df: pd.DataFrame, 
    title: str = "Line Chart", 
    x: Optional[str] = None,
    y: Optional[Union[str, List[str]]] = None,
    color: Optional[str] = None,
    **kwargs
) -> None:
    """Create and display a line chart"""
    # Auto-select columns if not provided
    if x is None:
        # Prefer datetime columns for x-axis
        date_columns = df.select_dtypes(include=["datetime64"]).columns
        if len(date_columns) > 0:
            x = date_columns[0]
        else:
            # Try to find a column that might be a date
            for col in df.columns:
                if "date" in col.lower() or "time" in col.lower() or "day" in col.lower():
                    try:
                        df[col] = pd.to_datetime(df[col])
                        x = col
                        break
                    except:
                        pass
            
            # If still no x, use the first column
            if x is None and len(df.columns) > 0:
                x = df.columns[0]
    
    if y is None:
        # Use all numeric columns except x as y
        num_columns = df.select_dtypes(include=["int64", "float64"]).columns
        y = [col for col in num_columns if col != x]
        
        # If no numeric columns found, use the second column
        if len(y) == 0 and len(df.columns) > 1:
            y = [df.columns[1]]
        elif len(y) == 0 and len(df.columns) > 0:
            y = [df.columns[0]]
    
    # Create chart with Plotly
    try:
        fig = px.line(
            df, 
            x=x, 
            y=y, 
            color=color,
            title=title,
            labels={col: col.replace("_", " ").title() for col in df.columns},
            height=kwargs.get("height", 500),
            markers=kwargs.get("markers", True),
            template="plotly_white"
        )
        
        # Update layout
        fig.update_layout(
            xaxis_title=kwargs.get("x_label", x),
            yaxis_title=kwargs.get("y_label", "Value" if isinstance(y, list) else y),
            legend_title=kwargs.get("legend_title", color),
            margin=dict(l=40, r=40, t=50, b=40)
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.error(f"Error creating line chart: {str(e)}")
        # Fallback to a simpler implementation using Altair
        try:
            if isinstance(y, list):
                # Melt the dataframe for multiple y columns
                id_vars = [x]
                if color:
                    id_vars.append(color)
                
                melted_df = pd.melt(df, id_vars=id_vars, value_vars=y, var_name="variable", value_name="value")
                
                chart = alt.Chart(melted_df).mark_line().encode(
                    x=x,
                    y="value:Q",
                    color="variable:N"
                ).properties(
                    title=title
                )
            else:
                chart = alt.Chart(df).mark_line().encode(
                    x=x,
                    y=y,
                    color=color
                ).properties(
                    title=title
                )
            
            st.altair_chart(chart, use_container_width=True)
        except:
            st.error("Could not create visualization with the selected columns")
            # Show data as table
            st.write(df)

def create_scatter_plot(
    df: pd.DataFrame, 
    title: str = "Scatter Plot", 
    x: Optional[str] = None,
    y: Optional[str] = None,
    color: Optional[str] = None,
    size: Optional[str] = None,
    **kwargs
) -> None:
    """Create and display a scatter plot"""
    # Auto-select columns if not provided
    if x is None or y is None:
        # Use numeric columns for scatter plots
        num_columns = df.select_dtypes(include=["int64", "float64"]).columns
        
        if len(num_columns) >= 2:
            if x is None:
                x = num_columns[0]
            if y is None:
                # Use a different column for y
                for col in num_columns:
                    if col != x:
                        y = col
                        break
        else:
            # If not enough numeric columns, use the first two columns
            if x is None and len(df.columns) > 0:
                x = df.columns[0]
            if y is None and len(df.columns) > 1:
                y = df.columns[1]
    
    # Create chart with Plotly
    try:
        fig = px.scatter(
            df, 
            x=x, 
            y=y, 
            color=color,
            size=size,
            title=title,
            labels={col: col.replace("_", " ").title() for col in df.columns},
            height=kwargs.get("height", 500),
            template="plotly_white"
        )
        
        # Update layout
        fig.update_layout(
            xaxis_title=kwargs.get("x_label", x),
            yaxis_title=kwargs.get("y_label", y),
            legend_title=kwargs.get("legend_title", color),
            margin=dict(l=40, r=40, t=50, b=40)
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.error(f"Error creating scatter plot: {str(e)}")
        # Fallback to a simpler implementation using Altair
        try:
            chart = alt.Chart(df).mark_circle().encode(
                x=x,
                y=y,
                color=color,
                size=size
            ).properties(
                title=title
            )
            
            st.altair_chart(chart, use_container_width=True)
        except:
            st.error("Could not create visualization with the selected columns")
            # Show data as table
            st.write(df)

def create_pie_chart(
    df: pd.DataFrame, 
    title: str = "Pie Chart", 
    names: Optional[str] = None,
    values: Optional[str] = None,
    **kwargs
) -> None:
    """Create and display a pie chart"""
    # Auto-select columns if not provided
    if names is None or values is None:
        # Use categorical column for names and numeric column for values
        cat_columns = df.select_dtypes(include=["object", "category", "bool"]).columns
        num_columns = df.select_dtypes(include=["int64", "float64"]).columns
        
        if len(cat_columns) > 0 and len(num_columns) > 0:
            if names is None:
                names = cat_columns[0]
            if values is None:
                values = num_columns[0]
        else:
            # Fallback to first two columns
            if names is None and len(df.columns) > 0:
                names = df.columns[0]
            if values is None and len(df.columns) > 1:
                values = df.columns[1]
            elif values is None and len(df.columns) > 0:
                # If only one column, create a count column
                values = "count"
                df[values] = 1
    
    # Create chart with Plotly
    try:
        fig = px.pie(
            df, 
            names=names, 
            values=values,
            title=title,
            labels={col: col.replace("_", " ").title() for col in df.columns},
            height=kwargs.get("height", 500),
            template="plotly_white"
        )
        
        # Update layout
        fig.update_layout(
            margin=dict(l=40, r=40, t=50, b=40)
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.error(f"Error creating pie chart: {str(e)}")
        # Fallback to a simpler implementation using Matplotlib
        try:
            fig, ax = plt.subplots(figsize=(10, 6))
            df.groupby(names)[values].sum().plot.pie(ax=ax, autopct='%1.1f%%')
            ax.set_title(title)
            ax.set_ylabel('')
            
            st.pyplot(fig)
        except:
            st.error("Could not create visualization with the selected columns")
            # Show data as table
            st.write(df)

def create_histogram(
    df: pd.DataFrame, 
    title: str = "Histogram", 
    x: Optional[str] = None,
    nbins: int = 20,
    color: Optional[str] = None,
    **kwargs
) -> None:
    """Create and display a histogram"""
    # Auto-select column if not provided
    if x is None:
        # Use numeric column for histogram
        num_columns = df.select_dtypes(include=["int64", "float64"]).columns
        
        if len(num_columns) > 0:
            x = num_columns[0]
        else:
            # Fallback to first column
            if len(df.columns) > 0:
                x = df.columns[0]
    
    # Create chart with Plotly
    try:
        fig = px.histogram(
            df, 
            x=x, 
            color=color,
            nbins=nbins,
            title=title,
            labels={col: col.replace("_", " ").title() for col in df.columns},
            height=kwargs.get("height", 500),
            template="plotly_white"
        )
        
        # Update layout
        fig.update_layout(
            xaxis_title=kwargs.get("x_label", x),
            yaxis_title=kwargs.get("y_label", "Count"),
            legend_title=kwargs.get("legend_title", color),
            margin=dict(l=40, r=40, t=50, b=40)
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.error(f"Error creating histogram: {str(e)}")
        # Fallback to a simpler implementation using Matplotlib
        try:
            fig, ax = plt.subplots(figsize=(10, 6))
            df[x].hist(bins=nbins, ax=ax)
            ax.set_title(title)
            ax.set_xlabel(x)
            ax.set_ylabel("Count")
            
            st.pyplot(fig)
        except:
            st.error("Could not create visualization with the selected columns")
            # Show data as table
            st.write(df)

def create_heatmap(
    df: pd.DataFrame, 
    title: str = "Heatmap", 
    x: Optional[str] = None,
    y: Optional[str] = None,
    values: Optional[str] = None,
    **kwargs
) -> None:
    """Create and display a heatmap"""
    # Auto-select columns if not provided
    if x is None or y is None or values is None:
        # Use categorical columns for x and y, numeric column for values
        cat_columns = df.select_dtypes(include=["object", "category", "bool"]).columns
        num_columns = df.select_dtypes(include=["int64", "float64"]).columns
        
        if len(cat_columns) >= 2 and len(num_columns) > 0:
            if x is None:
                x = cat_columns[0]
            if y is None:
                # Use a different column for y
                for col in cat_columns:
                    if col != x:
                        y = col
                        break
            if values is None:
                values = num_columns[0]
        else:
            # Fallback to first three columns
            if x is None and len(df.columns) > 0:
                x = df.columns[0]
            if y is None and len(df.columns) > 1:
                y = df.columns[1]
            if values is None and len(df.columns) > 2:
                values = df.columns[2]
            elif values is None and len(num_columns) > 0:
                values = num_columns[0]
    
    # Create a pivot table
    try:
        pivot_df = df.pivot_table(index=y, columns=x, values=values, aggfunc='mean')
        
        # Create chart with Plotly
        fig = px.imshow(
            pivot_df,
            title=title,
            labels=dict(
                x=x.replace("_", " ").title(),
                y=y.replace("_", " ").title(),
                color=values.replace("_", " ").title()
            ),
            height=kwargs.get("height", 500),
            color_continuous_scale=kwargs.get("colorscale", "Viridis"),
            template="plotly_white"
        )
        
        # Update layout
        fig.update_layout(
            margin=dict(l=40, r=40, t=50, b=40)
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.error(f"Error creating heatmap: {str(e)}")
        # Fallback to showing the data
        st.error("Could not create heatmap with the selected columns")
        st.write(df)

def create_box_plot(
    df: pd.DataFrame, 
    title: str = "Box Plot", 
    x: Optional[str] = None,
    y: Optional[str] = None,
    color: Optional[str] = None,
    **kwargs
) -> None:
    """Create and display a box plot"""
    # Auto-select columns if not provided
    if y is None:
        # Use numeric column for y
        num_columns = df.select_dtypes(include=["int64", "float64"]).columns
        
        if len(num_columns) > 0:
            y = num_columns[0]
        else:
            # Fallback to second column
            if len(df.columns) > 1:
                y = df.columns[1]
            elif len(df.columns) > 0:
                y = df.columns[0]
    
    if x is None:
        # Use categorical column for x
        cat_columns = df.select_dtypes(include=["object", "category", "bool"]).columns
        
        if len(cat_columns) > 0:
            x = cat_columns[0]
        else:
            # Fallback to first column
            if len(df.columns) > 0 and df.columns[0] != y:
                x = df.columns[0]
            elif len(df.columns) > 1:
                x = df.columns[1]
    
    # Create chart with Plotly
    try:
        fig = px.box(
            df, 
            x=x, 
            y=y, 
            color=color,
            title=title,
            labels={col: col.replace("_", " ").title() for col in df.columns},
            height=kwargs.get("height", 500),
            template="plotly_white"
        )
        
        # Update layout
        fig.update_layout(
            xaxis_title=kwargs.get("x_label", x),
            yaxis_title=kwargs.get("y_label", y),
            legend_title=kwargs.get("legend_title", color),
            margin=dict(l=40, r=40, t=50, b=40)
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.error(f"Error creating box plot: {str(e)}")
        # Fallback to a simpler implementation using Matplotlib
        try:
            fig, ax = plt.subplots(figsize=(10, 6))
            df.boxplot(column=y, by=x, ax=ax)
            ax.set_title(title)
            ax.set_xlabel(x)
            ax.set_ylabel(y)
            
            st.pyplot(fig)
        except:
            st.error("Could not create visualization with the selected columns")
            # Show data as table
            st.write(df)

def create_area_chart(
    df: pd.DataFrame, 
    title: str = "Area Chart", 
    x: Optional[str] = None,
    y: Optional[Union[str, List[str]]] = None,
    color: Optional[str] = None,
    **kwargs
) -> None:
    """Create and display an area chart"""
    # Auto-select columns if not provided
    if x is None:
        # Prefer datetime columns for x-axis
        date_columns = df.select_dtypes(include=["datetime64"]).columns
        if len(date_columns) > 0:
            x = date_columns[0]
        else:
            # Try to find a column that might be a date
            for col in df.columns:
                if "date" in col.lower() or "time" in col.lower() or "day" in col.lower():
                    try:
                        df[col] = pd.to_datetime(df[col])
                        x = col
                        break
                    except:
                        pass
            
            # If still no x, use the first column
            if x is None and len(df.columns) > 0:
                x = df.columns[0]
    
    if y is None:
        # Use all numeric columns except x as y
        num_columns = df.select_dtypes(include=["int64", "float64"]).columns
        y = [col for col in num_columns if col != x]
        
        # If no numeric columns found, use the second column
        if len(y) == 0 and len(df.columns) > 1:
            y = [df.columns[1]]
        elif len(y) == 0 and len(df.columns) > 0:
            y = [df.columns[0]]
    
    # Create chart with Plotly
    try:
        fig = px.area(
            df, 
            x=x, 
            y=y, 
            color=color,
            title=title,
            labels={col: col.replace("_", " ").title() for col in df.columns},
            height=kwargs.get("height", 500),
            template="plotly_white"
        )
        
        # Update layout
        fig.update_layout(
            xaxis_title=kwargs.get("x_label", x),
            yaxis_title=kwargs.get("y_label", "Value" if isinstance(y, list) else y),
            legend_title=kwargs.get("legend_title", color),
            margin=dict(l=40, r=40, t=50, b=40)
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.error(f"Error creating area chart: {str(e)}")
        # Fallback to a simpler implementation using Altair
        try:
            if isinstance(y, list):
                # Melt the dataframe for multiple y columns
                id_vars = [x]
                if color:
                    id_vars.append(color)
                
                melted_df = pd.melt(df, id_vars=id_vars, value_vars=y, var_name="variable", value_name="value")
                
                chart = alt.Chart(melted_df).mark_area().encode(
                    x=x,
                    y="value:Q",
                    color="variable:N"
                ).properties(
                    title=title
                )
            else:
                chart = alt.Chart(df).mark_area().encode(
                    x=x,
                    y=y,
                    color=color
                ).properties(
                    title=title
                )
            
            st.altair_chart(chart, use_container_width=True)
        except:
            st.error("Could not create visualization with the selected columns")
            # Show data as table
            st.write(df)

def create_table(
    df: pd.DataFrame, 
    title: str = "Data Table", 
    **kwargs
) -> None:
    """Create and display a table"""
    st.subheader(title)
    
    # Format and display the table
    st.dataframe(
        df,
        height=kwargs.get("height", 400),
        use_container_width=True
    )
    
    # Show summary statistics if requested
    if kwargs.get("show_summary", False):
        st.subheader("Summary Statistics")
        
        # Get numeric columns for summary
        num_df = df.select_dtypes(include=["int64", "float64"])
        
        if not num_df.empty:
            st.dataframe(
                num_df.describe(),
                use_container_width=True
            )
        else:
            st.info("No numeric columns for summary statistics")

def create_map(
    df: pd.DataFrame, 
    title: str = "Map", 
    lat: Optional[str] = None,
    lon: Optional[str] = None,
    color: Optional[str] = None,
    size: Optional[str] = None,
    **kwargs
) -> None:
    """Create and display a map"""
    # Auto-detect lat/lon columns if not provided
    if lat is None or lon is None:
        # Common column names for latitude and longitude
        lat_names = ["lat", "latitude", "Lat", "Latitude"]
        lon_names = ["lon", "lng", "longitude", "Lon", "Lng", "Longitude"]
        
        # Find latitude column
        if lat is None:
            for name in lat_names:
                if name in df.columns:
                    lat = name
                    break
        
        # Find longitude column
        if lon is None:
            for name in lon_names:
                if name in df.columns:
                    lon = name
                    break
    
    # Check if we have lat/lon columns
    if lat is None or lon is None:
        st.error("Could not identify latitude and longitude columns for the map")
        # Show data as table
        create_table(df, title, **kwargs)
        return
    
    # Create map with Plotly
    try:
        # Default to scatter mapbox
        fig = px.scatter_mapbox(
            df,
            lat=lat,
            lon=lon,
            color=color,
            size=size,
            title=title,
            labels={col: col.replace("_", " ").title() for col in df.columns},
            height=kwargs.get("height", 500),
            template="plotly_white",
            mapbox_style="open-street-map"
        )
        
        # Update layout
        fig.update_layout(
            margin=dict(l=0, r=0, t=50, b=0)
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.error(f"Error creating map: {str(e)}")
        # Fallback to table view
        st.error("Could not create map with the selected columns")
        create_table(df, title, **kwargs)

def visualization_interface(api_client: Optional[APIClient] = None):
    """
    Create an interactive visualization interface
    
    Args:
        api_client: API client instance (optional)
    """
    st.title("Data Visualization")
    
    # Data source selection
    data_source = st.radio(
        "Select data source",
        ["Upload File", "Paste Data", "Sample Dataset"],
        horizontal=True
    )
    
    # Initialize data
    data = None
    
    # Handle different data sources
    if data_source == "Upload File":
        uploaded_file = st.file_uploader(
            "Upload a CSV or Excel file",
            type=["csv", "xlsx", "xls", "json"]
        )
        
        if uploaded_file:
            try:
                # Determine file type
                file_ext = uploaded_file.name.split(".")[-1].lower()
                
                if file_ext == "csv":
                    data = pd.read_csv(uploaded_file)
                elif file_ext in ["xlsx", "xls"]:
                    data = pd.read_excel(uploaded_file)
                elif file_ext == "json":
                    data = pd.read_json(uploaded_file)
                
                st.success(f"Loaded data with {data.shape[0]} rows and {data.shape[1]} columns")
                
            except Exception as e:
                st.error(f"Error loading file: {str(e)}")
    
    elif data_source == "Paste Data":
        data_format = st.selectbox(
            "Data format",
            ["CSV", "JSON", "Excel (not supported for pasting)"]
        )
        
        data_text = st.text_area(
            "Paste your data here",
            height=200,
            placeholder="Paste CSV or JSON data..."
        )
        
        if data_text:
            try:
                if data_format == "CSV":
                    data = pd.read_csv(io.StringIO(data_text))
                elif data_format == "JSON":
                    data = pd.read_json(io.StringIO(data_text))
                
                st.success(f"Loaded data with {data.shape[0]} rows and {data.shape[1]} columns")
                
            except Exception as e:
                st.error(f"Error parsing data: {str(e)}")
    
    elif data_source == "Sample Dataset":
        sample_dataset = st.selectbox(
            "Select a sample dataset",
            ["Solar Panel Performance", "Energy Production by Source", "Installation Costs", "Battery Efficiency"]
        )
        
        # Load sample dataset
        if sample_dataset == "Solar Panel Performance":
            # Create sample data for solar panel performance
            dates = pd.date_range(start="2023-01-01", periods=365, freq="D")
            power_output = 5 + 3 * np.sin(np.linspace(0, 2*np.pi, 365)) + np.random.normal(0, 0.5, 365)
            temperature = 25 + 15 * np.sin(np.linspace(0, 2*np.pi, 365)) + np.random.normal(0, 3, 365)
            efficiency = 18 - 0.1 * temperature + np.random.normal(0, 0.5, 365)
            
            data = pd.DataFrame({
                "Date": dates,
                "Power_Output_kW": power_output,
                "Temperature_C": temperature,
                "Efficiency_Percent": efficiency
            })
            
        elif sample_dataset == "Energy Production by Source":
            # Create sample data for energy production by source
            sources = ["Solar", "Wind", "Hydro", "Nuclear", "Gas", "Coal"]
            years = list(range(2010, 2023))
            
            production_data = []
            for year in years:
                for source in sources:
                    if source == "Solar":
                        # Solar grows faster
                        base = 10 + (year - 2010) * 8
                    elif source == "Wind":
                        # Wind grows moderately
                        base = 30 + (year - 2010) * 5
                    elif source == "Hydro":
                        # Hydro stays relatively constant
                        base = 40 + (year - 2010) * 0.5
                    elif source == "Nuclear":
                        # Nuclear stays constant
                        base = 35
                    elif source == "Gas":
                        # Gas declines slowly
                        base = 50 - (year - 2010) * 1
                    else:  # Coal
                        # Coal declines faster
                        base = 60 - (year - 2010) * 3
                    
                    # Add some random variation
                    production = max(0, base + np.random.normal(0, base*0.05))
                    
                    production_data.append({
                        "Year": year,
                        "Source": source,
                        "Production_TWh": production
                    })
            
            data = pd.DataFrame(production_data)
            
        elif sample_dataset == "Installation Costs":
            # Create sample data for installation costs
            system_sizes = [3, 5, 8, 10, 15, 20, 25, 30]
            installation_types = ["Residential", "Commercial", "Industrial"]
            
            cost_data = []
            for size in system_sizes:
                for installation in installation_types:
                    if installation == "Residential":
                        # Higher cost per kW for residential
                        base_cost = 2800 - (size - 3) * 50
                    elif installation == "Commercial":
                        # Medium cost for commercial
                        base_cost = 2400 - (size - 3) * 40
                    else:  # Industrial
                        # Lower cost per kW for industrial
                        base_cost = 2000 - (size - 3) * 30
                    
                    # Ensure minimum cost
                    base_cost = max(1500, base_cost)
                    
                    # Add some random variation
                    cost_per_kw = base_cost + np.random.normal(0, base_cost*0.05)
                    total_cost = size * cost_per_kw
                    
                    cost_data.append({
                        "System_Size_kW": size,
                        "Installation_Type": installation,
                        "Cost_Per_kW": cost_per_kw,
                        "Total_Cost": total_cost
                    })
            
            data = pd.DataFrame(cost_data)
            
        elif sample_dataset == "Battery Efficiency":
            # Create sample data for battery efficiency
            battery_types = ["Lithium Ion", "Lead Acid", "Flow Battery", "Solid State"]
            cycle_counts = list(range(0, 5001, 250))
            
            efficiency_data = []
            for battery in battery_types:
                for cycle in cycle_counts:
                    if battery == "Lithium Ion":
                        # Good cycle life
                        base_efficiency = 95 - (cycle / 5000) * 15
                    elif battery == "Lead Acid":
                        # Poor cycle life
                        base_efficiency = 85 - (cycle / 5000) * 25
                    elif battery == "Flow Battery":
                        # Excellent cycle life
                        base_efficiency = 80 - (cycle / 5000) * 8
                    else:  # Solid State
                        # Best cycle life
                        base_efficiency = 98 - (cycle / 5000) * 5
                    
                    # Add some random variation
                    efficiency = base_efficiency + np.random.normal(0, 1)
                    efficiency = min(100, max(0, efficiency))
                    
                    efficiency_data.append({
                        "Battery_Type": battery,
                        "Cycle_Count": cycle,
                        "Efficiency_Percent": efficiency
                    })
            
            data = pd.DataFrame(efficiency_data)
    
    # Visualization options if data is loaded
    if data is not None:
        # Show data preview
        with st.expander("Data Preview"):
            st.dataframe(data.head(10), use_container_width=True)
            
            # Show column info
            st.subheader("Column Information")
            info_df = pd.DataFrame({
                "Column": data.columns,
                "Type": data.dtypes.astype(str),
                "Non-Null Values": data.count().values,
                "Null Values": data.isna().sum().values,
                "Unique Values": [data[col].nunique() for col in data.columns]
            })
            st.dataframe(info_df, use_container_width=True)
        
        # Visualization controls
        st.subheader("Visualization Controls")
        
        # Visualization type
        viz_types = [
            "auto", "bar", "line", "scatter", "pie", "histogram", 
            "heatmap", "box", "area", "table", "map"
        ]
        viz_type = st.selectbox("Visualization Type", viz_types)
        
        # Title
        title = st.text_input("Title", value="Data Visualization")
        
        # Column selection based on visualization type
        col1, col2 = st.columns(2)
        
        with col1:
            # X-axis column (or similar)
            x_label = "X-Axis"
            if viz_type in ["pie"]:
                x_label = "Names"
            elif viz_type in ["histogram"]:
                x_label = "Values"
            elif viz_type in ["map"]:
                x_label = "Latitude"
            
            x_column = st.selectbox(
                x_label,
                ["None"] + list(data.columns),
                index=0 if viz_type == "auto" else 1 if len(data.columns) > 0 else 0
            )
            x_column = None if x_column == "None" else x_column
        
        with col2:
            # Y-axis column (or similar)
            y_label = "Y-Axis"
            if viz_type in ["pie"]:
                y_label = "Values"
            elif viz_type in ["map"]:
                y_label = "Longitude"
            
            y_column = st.selectbox(
                y_label,
                ["None"] + list(data.columns),
                index=0 if viz_type == "auto" else min(2, len(data.columns)) if len(data.columns) > 1 else 0
            )
            y_column = None if y_column == "None" else y_column
        
        # Additional options based on visualization type
        additional_options = {}
        
        # Color column (for many chart types)
        if viz_type in ["bar", "line", "scatter", "box", "area", "map"]:
            color_column = st.selectbox(
                "Color By",
                ["None"] + list(data.columns),
                index=0
            )
            if color_column != "None":
                additional_options["color"] = color_column
        
        # Size column (for scatter and map)
        if viz_type in ["scatter", "map"]:
            size_column = st.selectbox(
                "Size By",
                ["None"] + list(data.columns),
                index=0
            )
            if size_column != "None":
                additional_options["size"] = size_column
        
        # Number of bins (for histogram)
        if viz_type in ["histogram"]:
            nbins = st.slider("Number of Bins", 5, 100, 20)
            additional_options["nbins"] = nbins
        
        # Create visualization
        if st.button("Generate Visualization"):
            st.subheader("Visualization Result")
            
            # Pass the appropriate arguments based on visualization type
            if viz_type in ["pie"]:
                visualize_data(
                    data, 
                    viz_type=viz_type,
                    title=title,
                    names=x_column,
                    values=y_column,
                    **additional_options
                )
            elif viz_type in ["map"]:
                visualize_data(
                    data, 
                    viz_type=viz_type,
                    title=title,
                    lat=x_column,
                    lon=y_column,
                    **additional_options
                )
            else:
                visualize_data(
                    data, 
                    viz_type=viz_type,
                    title=title,
                    x=x_column,
                    y=y_column,
                    **additional_options
                )
            
            # Show data summary
            with st.expander("Data Summary"):
                # Get numeric columns for summary
                num_df = data.select_dtypes(include=["int64", "float64"])
                
                if not num_df.empty:
                    st.dataframe(
                        num_df.describe(),
                        use_container_width=True
                    )
                else:
                    st.info("No numeric columns for summary statistics")
            
            # Option to export visualization
            st.download_button(
                label="Export Data as CSV",
                data=data.to_csv(index=False).encode('utf-8'),
                file_name=f"{title.replace(' ', '_')}.csv",
                mime="text/csv"
            )