import os
import json
import base64
from typing import Dict, Any, List, Optional, Union, Tuple
import io
import tempfile
import uuid
from datetime import datetime

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.figure import Figure
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio

from backend.utils.logging import setup_logger
from backend.utils.cache import get_cache, set_cache
from backend.config import settings
from backend.models.model_loader import model_loader

logger = setup_logger("viz_agent")

class VisualizationAgent:
    """
    Agent for creating data visualizations based on user data and requests.
    Features:
    - Multiple visualization types (charts, plots, graphs)
    - Custom styling options
    - Interactive visualizations
    - Data preprocessing
    - Intelligent chart type selection
    """
    
    def __init__(self):
        self.visualization_types = {
            "bar": self._create_bar_chart,
            "line": self._create_line_chart,
            "scatter": self._create_scatter_plot,
            "pie": self._create_pie_chart,
            "histogram": self._create_histogram,
            "heatmap": self._create_heatmap,
            "box": self._create_box_plot,
            "violin": self._create_violin_plot,
            "sunburst": self._create_sunburst,
            "sankey": self._create_sankey,
            "table": self._create_table,
            "map": self._create_map,
            "timeseries": self._create_timeseries
        }
        
        # Default visualization options
        self.default_width = 1000
        self.default_height = 600
        self.default_color_palette = "viridis"
        self.default_theme = "plotly_white"
        
        # Set default Plotly theme
        pio.templates.default = self.default_theme
        
        # Create visualizations directory if it doesn't exist
        self.viz_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "visualizations")
        os.makedirs(self.viz_dir, exist_ok=True)
    
    async def create_visualization(
        self,
        data: Union[str, pd.DataFrame, Dict[str, Any], List[Dict[str, Any]]],
        viz_type: Optional[str] = None,
        title: str = "Visualization",
        description: str = "",
        options: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        interactive: bool = True
    ) -> Dict[str, Any]:
        """
        Create a visualization based on the provided data
        
        Args:
            data: Data to visualize (DataFrame, dict, list of dicts, or CSV/JSON string)
            viz_type: Type of visualization (bar, line, etc.), auto-detected if not provided
            title: Visualization title
            description: Visualization description
            options: Additional visualization options
            user_id: User ID for tracking
            interactive: Whether to create an interactive visualization
            
        Returns:
            Dict containing visualization details and encoded image
        """
        start_time = datetime.utcnow()
        options = options or {}
        
        try:
            # Process data into a DataFrame
            df = self._process_data(data)
            
            # Auto-detect visualization type if not provided
            if not viz_type:
                viz_type = await self._auto_select_viz_type(df, options)
                logger.info(f"Auto-selected visualization type: {viz_type}")
            
            # Validate visualization type
            if viz_type not in self.visualization_types:
                logger.warning(f"Invalid visualization type: {viz_type}, defaulting to bar")
                viz_type = "bar"
            
            # Create visualization
            logger.info(f"Creating {viz_type} visualization")
            viz_function = self.visualization_types[viz_type]
            
            if interactive:
                fig = viz_function(df, title=title, **options)
                
                # Save interactive visualization to HTML
                viz_id = str(uuid.uuid4())
                html_path = os.path.join(self.viz_dir, f"{viz_id}.html")
                json_path = os.path.join(self.viz_dir, f"{viz_id}.json")
                
                try:
                    # Save as HTML
                    pio.write_html(fig, file=html_path, auto_open=False)
                    
                    # Save metadata
                    metadata = {
                        "id": viz_id,
                        "title": title,
                        "description": description,
                        "type": viz_type,
                        "user_id": user_id,
                        "created_at": start_time.isoformat(),
                        "options": options
                    }
                    
                    with open(json_path, 'w') as f:
                        json.dump(metadata, f)
                    
                    # Generate preview image
                    img_bytes = self._fig_to_base64(fig)
                    
                    return {
                        "id": viz_id,
                        "title": title,
                        "description": description,
                        "type": viz_type,
                        "created_at": start_time.isoformat(),
                        "image": img_bytes,
                        "html_path": html_path,
                        "interactive": True
                    }
                    
                except Exception as e:
                    logger.error(f"Error saving interactive visualization: {str(e)}")
                    # Fall back to static image
                    interactive = False
            
            if not interactive:
                # Create static image
                fig = viz_function(df, title=title, **options)
                img_bytes = self._fig_to_base64(fig)
                
                viz_id = str(uuid.uuid4())
                img_path = os.path.join(self.viz_dir, f"{viz_id}.png")
                json_path = os.path.join(self.viz_dir, f"{viz_id}.json")
                
                # Save image and metadata
                with open(img_path, 'wb') as f:
                    img_data = base64.b64decode(img_bytes.split(',')[1])
                    f.write(img_data)
                
                metadata = {
                    "id": viz_id,
                    "title": title,
                    "description": description,
                    "type": viz_type,
                    "user_id": user_id,
                    "created_at": start_time.isoformat(),
                    "options": options
                }
                
                with open(json_path, 'w') as f:
                    json.dump(metadata, f)
                
                return {
                    "id": viz_id,
                    "title": title,
                    "description": description,
                    "type": viz_type,
                    "created_at": start_time.isoformat(),
                    "image": img_bytes,
                    "img_path": img_path,
                    "interactive": False
                }
                
        except Exception as e:
            logger.error(f"Error creating visualization: {str(e)}")
            return {
                "error": str(e),
                "created_at": start_time.isoformat()
            }
    
    def _process_data(self, data: Union[str, pd.DataFrame, Dict[str, Any], List[Dict[str, Any]]]) -> pd.DataFrame:
        """
        Process input data into a pandas DataFrame
        
        Args:
            data: Input data in various formats
            
        Returns:
            Processed pandas DataFrame
        """
        if isinstance(data, pd.DataFrame):
            return data
        
        if isinstance(data, dict):
            return pd.DataFrame.from_dict(data)
        
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
                if isinstance(json_data, dict):
                    return pd.DataFrame.from_dict(json_data)
            except:
                pass
        
        raise ValueError("Unsupported data format. Please provide a DataFrame, dict, list of dicts, or CSV/JSON string.")
    
    async def _auto_select_viz_type(self, df: pd.DataFrame, options: Dict[str, Any]) -> str:
        """
        Automatically select the best visualization type based on the data
        
        Args:
            df: Input DataFrame
            options: Visualization options
            
        Returns:
            Recommended visualization type
        """
        # If options specify columns to use, filter the DataFrame
        x_col = options.get("x")
        y_col = options.get("y")
        
        if x_col and y_col:
            # Check if both columns exist
            if x_col in df.columns and y_col in df.columns:
                # Check column types
                x_type = df[x_col].dtype
                y_type = df[y_col].dtype
                
                # Date/time vs numeric: line or timeseries
                if pd.api.types.is_datetime64_any_dtype(x_type) and pd.api.types.is_numeric_dtype(y_type):
                    return "timeseries"
                
                # Categorical vs numeric: bar chart
                if pd.api.types.is_object_dtype(x_type) and pd.api.types.is_numeric_dtype(y_type):
                    if df[x_col].nunique() <= 30:  # Reasonable number of categories
                        return "bar"
                
                # Numeric vs numeric: scatter plot
                if pd.api.types.is_numeric_dtype(x_type) and pd.api.types.is_numeric_dtype(y_type):
                    return "scatter"
        
        # For other cases, look at the overall DataFrame structure
        num_columns = len(df.columns)
        num_rows = len(df)
        
        # Count categorical and numeric columns
        cat_cols = sum(1 for col in df.columns if pd.api.types.is_object_dtype(df[col].dtype))
        num_cols = sum(1 for col in df.columns if pd.api.types.is_numeric_dtype(df[col].dtype))
        
        # Check for datetime columns
        date_cols = sum(1 for col in df.columns if pd.api.types.is_datetime64_any_dtype(df[col].dtype))
        
        # Simple rules for recommendation
        if date_cols > 0 and num_cols > 0:
            return "timeseries"
        
        if cat_cols == 1 and num_cols > 0:
            if df.select_dtypes(include=['object']).iloc[:, 0].nunique() <= 10:
                return "bar"
        
        if cat_cols >= 2 and num_cols > 0:
            return "heatmap"
        
        if num_cols >= 2:
            # If many rows, histogram or scatter
            if num_rows > 100:
                return "scatter"
            return "line"
        
        if cat_cols == 1 and num_cols == 1:
            # One categorical, one numeric
            return "bar"
        
        # Default to bar chart
        return "bar"
    
    def _fig_to_base64(self, fig: Any) -> str:
        """
        Convert a figure to base64 encoded image
        
        Args:
            fig: Figure to convert (Matplotlib or Plotly)
            
        Returns:
            Base64 encoded image string
        """
        # Handle Plotly figures
        if 'plotly' in str(type(fig)):
            img_bytes = pio.to_image(fig, format="png")
            encoded = base64.b64encode(img_bytes).decode('utf-8')
            return f"data:image/png;base64,{encoded}"
        
        # Handle Matplotlib figures
        if isinstance(fig, Figure):
            buf = io.BytesIO()
            fig.savefig(buf, format='png', bbox_inches='tight')
            buf.seek(0)
            encoded = base64.b64encode(buf.read()).decode('utf-8')
            plt.close(fig)
            return f"data:image/png;base64,{encoded}"
        
        raise ValueError("Unsupported figure type")
    
    def _create_bar_chart(
        self, 
        df: pd.DataFrame, 
        x: Optional[str] = None,
        y: Optional[str] = None,
        title: str = "Bar Chart",
        orientation: str = "v",
        color: Optional[str] = None,
        **kwargs
    ) -> Any:
        """Create a bar chart"""
        # Auto-select columns if not provided
        if not x:
            # Select first categorical column
            for col in df.columns:
                if pd.api.types.is_object_dtype(df[col].dtype) or df[col].nunique() < 20:
                    x = col
                    break
            
            # If no categorical column found, use the index
            if not x:
                df = df.reset_index()
                x = "index"
        
        if not y:
            # Select first numeric column
            for col in df.columns:
                if pd.api.types.is_numeric_dtype(df[col].dtype) and col != x:
                    y = col
                    break
        
        # Create figure
        if orientation == "h":
            fig = px.bar(
                df, 
                y=x, 
                x=y, 
                title=title,
                color=color,
                orientation="h",
                width=self.default_width,
                height=self.default_height,
                **kwargs
            )
        else:
            fig = px.bar(
                df, 
                x=x, 
                y=y, 
                title=title,
                color=color,
                width=self.default_width,
                height=self.default_height,
                **kwargs
            )
        
        # Update layout
        fig.update_layout(
            title_x=0.5,
            xaxis_title=x,
            yaxis_title=y,
            legend_title=color if color else "",
            template=self.default_theme
        )
        
        return fig
    
    def _create_line_chart(
        self, 
        df: pd.DataFrame, 
        x: Optional[str] = None,
        y: Optional[Union[str, List[str]]] = None,
        title: str = "Line Chart",
        color: Optional[str] = None,
        **kwargs
    ) -> Any:
        """Create a line chart"""
        # Auto-select columns if not provided
        if not x:
            # Try to use a datetime column
            for col in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[col].dtype):
                    x = col
                    break
            
            # If no datetime column, use first column
            if not x:
                x = df.columns[0]
        
        if not y:
            # Use all numeric columns except x
            y = [col for col in df.columns if pd.api.types.is_numeric_dtype(df[col].dtype) and col != x]
            
            # If no numeric columns found, use the second column
            if not y and len(df.columns) > 1:
                y = [df.columns[1]]
        
        # Create figure
        fig = px.line(
            df, 
            x=x, 
            y=y, 
            title=title,
            color=color,
            width=self.default_width,
            height=self.default_height,
            **kwargs
        )
        
        # Update layout
        fig.update_layout(
            title_x=0.5,
            xaxis_title=x,
            yaxis_title=y if isinstance(y, str) else "Value",
            legend_title=color if color else "",
            template=self.default_theme
        )
        
        return fig
    
    def _create_scatter_plot(
        self, 
        df: pd.DataFrame, 
        x: Optional[str] = None,
        y: Optional[str] = None,
        title: str = "Scatter Plot",
        color: Optional[str] = None,
        size: Optional[str] = None,
        **kwargs
    ) -> Any:
        """Create a scatter plot"""
        # Auto-select columns if not provided
        if not x or not y:
            # Select first two numeric columns
            numeric_cols = [col for col in df.columns if pd.api.types.is_numeric_dtype(df[col].dtype)]
            
            if len(numeric_cols) >= 2:
                if not x:
                    x = numeric_cols[0]
                if not y:
                    y = numeric_cols[1]
            else:
                # Fall back to first two columns
                if not x:
                    x = df.columns[0]
                if not y and len(df.columns) > 1:
                    y = df.columns[1]
        
        # Create figure
        fig = px.scatter(
            df, 
            x=x, 
            y=y, 
            title=title,
            color=color,
            size=size,
            width=self.default_width,
            height=self.default_height,
            **kwargs
        )
        
        # Update layout
        fig.update_layout(
            title_x=0.5,
            xaxis_title=x,
            yaxis_title=y,
            legend_title=color if color else "",
            template=self.default_theme
        )
        
        return fig
    
    def _create_pie_chart(
        self, 
        df: pd.DataFrame, 
        names: Optional[str] = None,
        values: Optional[str] = None,
        title: str = "Pie Chart",
        **kwargs
    ) -> Any:
        """Create a pie chart"""
        # Auto-select columns if not provided
        if not names:
            # Select first categorical column
            for col in df.columns:
                if pd.api.types.is_object_dtype(df[col].dtype) or df[col].nunique() < 20:
                    names = col
                    break
            
            # If no categorical column found, use the first column
            if not names:
                names = df.columns[0]
        
        if not values:
            # Select first numeric column
            for col in df.columns:
                if pd.api.types.is_numeric_dtype(df[col].dtype) and col != names:
                    values = col
                    break
            
            # If no numeric column found, create a count column
            if not values:
                df = df.copy()
                df['count'] = 1
                values = 'count'
        
        # Create figure
        fig = px.pie(
            df, 
            names=names, 
            values=values, 
            title=title,
            width=self.default_width,
            height=self.default_height,
            **kwargs
        )
        
        # Update layout
        fig.update_layout(
            title_x=0.5,
            template=self.default_theme
        )
        
        return fig
    
    def _create_histogram(
        self, 
        df: pd.DataFrame, 
        x: Optional[str] = None,
        title: str = "Histogram",
        nbins: int = 50,
        color: Optional[str] = None,
        **kwargs
    ) -> Any:
        """Create a histogram"""
        # Auto-select column if not provided
        if not x:
            # Select first numeric column
            for col in df.columns:
                if pd.api.types.is_numeric_dtype(df[col].dtype):
                    x = col
                    break
            
            # If no numeric column found, use the first column
            if not x:
                x = df.columns[0]
        
        # Create figure
        fig = px.histogram(
            df, 
            x=x, 
            title=title,
            nbins=nbins,
            color=color,
            width=self.default_width,
            height=self.default_height,
            **kwargs
        )
        
        # Update layout
        fig.update_layout(
            title_x=0.5,
            xaxis_title=x,
            yaxis_title="Count",
            legend_title=color if color else "",
            template=self.default_theme
        )
        
        return fig
    
    def _create_heatmap(
        self, 
        df: pd.DataFrame, 
        x: Optional[str] = None,
        y: Optional[str] = None,
        z: Optional[str] = None,
        title: str = "Heatmap",
        **kwargs
    ) -> Any:
        """Create a heatmap"""
        # Check if we have a pivot table or need to create one
        if df.index.nlevels <= 1 and df.columns.nlevels <= 1:
            # Auto-select columns if not provided
            if not x or not y or not z:
                # Need at least 2 categorical and 1 numeric column
                cat_cols = [col for col in df.columns if pd.api.types.is_object_dtype(df[col].dtype) or df[col].nunique() < 20]
                num_cols = [col for col in df.columns if pd.api.types.is_numeric_dtype(df[col].dtype)]
                
                if len(cat_cols) >= 2 and len(num_cols) >= 1:
                    if not x:
                        x = cat_cols[0]
                    if not y:
                        y = cat_cols[1]
                    if not z:
                        z = num_cols[0]
                else:
                    raise ValueError("Heatmap requires at least 2 categorical columns and 1 numeric column")
            
            # Create pivot table
            pivot_df = df.pivot_table(index=y, columns=x, values=z, aggfunc='mean')
        else:
            # Already a pivot table or multi-index DataFrame
            pivot_df = df
        
        # Create figure
        fig = px.imshow(
            pivot_df,
            title=title,
            width=self.default_width,
            height=self.default_height,
            color_continuous_scale=self.default_color_palette,
            **kwargs
        )
        
        # Update layout
        fig.update_layout(
            title_x=0.5,
            xaxis_title=x if x else "",
            yaxis_title=y if y else "",
            coloraxis_colorbar_title=z if z else "Value",
            template=self.default_theme
        )
        
        return fig
    
    def _create_box_plot(
        self, 
        df: pd.DataFrame, 
        x: Optional[str] = None,
        y: Optional[str] = None,
        title: str = "Box Plot",
        color: Optional[str] = None,
        **kwargs
    ) -> Any:
        """Create a box plot"""
        # Auto-select columns if not provided
        if not x and not y:
            # Select first categorical and first numeric column
            cat_cols = [col for col in df.columns if pd.api.types.is_object_dtype(df[col].dtype) or df[col].nunique() < 20]
            num_cols = [col for col in df.columns if pd.api.types.is_numeric_dtype(df[col].dtype)]
            
            if len(cat_cols) >= 1 and len(num_cols) >= 1:
                x = cat_cols[0]
                y = num_cols[0]
            elif len(num_cols) >= 1:
                # If no categorical column, just use the numeric column
                y = num_cols[0]
            else:
                # Fall back to first two columns
                x = df.columns[0]
                if len(df.columns) > 1:
                    y = df.columns[1]
        
        # Create figure
        fig = px.box(
            df, 
            x=x, 
            y=y, 
            title=title,
            color=color,
            width=self.default_width,
            height=self.default_height,
            **kwargs
        )
        
        # Update layout
        fig.update_layout(
            title_x=0.5,
            xaxis_title=x if x else "",
            yaxis_title=y if y else "",
            legend_title=color if color else "",
            template=self.default_theme
        )
        
        return fig
    
    def _create_violin_plot(
        self, 
        df: pd.DataFrame, 
        x: Optional[str] = None,
        y: Optional[str] = None,
        title: str = "Violin Plot",
        color: Optional[str] = None,
        **kwargs
    ) -> Any:
        """Create a violin plot"""
        # Auto-select columns if not provided
        if not x and not y:
            # Select first categorical and first numeric column
            cat_cols = [col for col in df.columns if pd.api.types.is_object_dtype(df[col].dtype) or df[col].nunique() < 20]
            num_cols = [col for col in df.columns if pd.api.types.is_numeric_dtype(df[col].dtype)]
            
            if len(cat_cols) >= 1 and len(num_cols) >= 1:
                x = cat_cols[0]
                y = num_cols[0]
            elif len(num_cols) >= 1:
                # If no categorical column, just use the numeric column
                y = num_cols[0]
            else:
                # Fall back to first two columns
                x = df.columns[0]
                if len(df.columns) > 1:
                    y = df.columns[1]
        
        # Create figure
        fig = px.violin(
            df, 
            x=x, 
            y=y, 
            title=title,
            color=color,
            width=self.default_width,
            height=self.default_height,
            box=True,  # Include box plot inside violin
            **kwargs
        )
        
        # Update layout
        fig.update_layout(
            title_x=0.5,
            xaxis_title=x if x else "",
            yaxis_title=y if y else "",
            legend_title=color if color else "",
            template=self.default_theme
        )
        
        return fig
    
    def _create_sunburst(
        self, 
        df: pd.DataFrame, 
        path: Optional[List[str]] = None,
        values: Optional[str] = None,
        title: str = "Sunburst Chart",
        **kwargs
    ) -> Any:
        """Create a sunburst chart"""
        # Auto-select columns if not provided
        if not path:
            # Select categorical columns
            cat_cols = [col for col in df.columns if pd.api.types.is_object_dtype(df[col].dtype) or df[col].nunique() < 20]
            
            if len(cat_cols) >= 2:
                path = cat_cols[:3]  # Use up to 3 categorical columns
            else:
                # Fall back to first column
                path = [df.columns[0]]
        
        if not values:
            # Select first numeric column
            for col in df.columns:
                if pd.api.types.is_numeric_dtype(df[col].dtype) and col not in path:
                    values = col
                    break
            
            # If no numeric column found, create a count column
            if not values:
                df = df.copy()
                df['count'] = 1
                values = 'count'
        
        # Create figure
        fig = px.sunburst(
            df, 
            path=path, 
            values=values, 
            title=title,
            width=self.default_width,
            height=self.default_height,
            **kwargs
        )
        
        # Update layout
        fig.update_layout(
            title_x=0.5,
            template=self.default_theme
        )
        
        return fig
    
    def _create_sankey(
        self, 
        df: pd.DataFrame, 
        source: Optional[str] = None,
        target: Optional[str] = None,
        value: Optional[str] = None,
        title: str = "Sankey Diagram",
        **kwargs
    ) -> Any:
        """Create a sankey diagram"""
        # Auto-select columns if not provided
        if not source or not target:
            # Select first two categorical columns
            cat_cols = [col for col in df.columns if pd.api.types.is_object_dtype(df[col].dtype) or df[col].nunique() < 50]
            
            if len(cat_cols) >= 2:
                if not source:
                    source = cat_cols[0]
                if not target:
                    target = cat_cols[1]
            else:
                raise ValueError("Sankey diagram requires at least 2 categorical columns")
        
        if not value:
            # Select first numeric column
            for col in df.columns:
                if pd.api.types.is_numeric_dtype(df[col].dtype) and col != source and col != target:
                    value = col
                    break
            
            # If no numeric column found, create a count column
            if not value:
                df = df.copy()
                df['count'] = 1
                value = 'count'
        
        # Process data for Sankey
        # Convert categorical columns to numeric indices
        source_mapping = {s: i for i, s in enumerate(df[source].unique())}
        target_mapping = {t: i + len(source_mapping) for i, t in enumerate(df[target].unique())}
        
        # Map sources and targets to indices
        sources = [source_mapping[s] for s in df[source]]
        targets = [target_mapping[t] for t in df[target]]
        values = df[value].tolist()
        
        # Create node labels
        node_labels = list(source_mapping.keys()) + list(target_mapping.keys())
        
        # Create figure
        fig = go.Figure(data=[go.Sankey(
            node=dict(
                pad=15,
                thickness=20,
                line=dict(color="black", width=0.5),
                label=node_labels
            ),
            link=dict(
                source=sources,
                target=targets,
                value=values
            )
        )])
        
        # Update layout
        fig.update_layout(
            title_text=title,
            title_x=0.5,
            width=self.default_width,
            height=self.default_height,
            template=self.default_theme
        )
        
        return fig
    
    def _create_table(
        self, 
        df: pd.DataFrame, 
        title: str = "Data Table",
        **kwargs
    ) -> Any:
        """Create a data table"""
        # Limit number of rows for performance
        if len(df) > 100:
            df = df.head(100)
        
        # Create figure
        fig = go.Figure(data=[go.Table(
            header=dict(
                values=list(df.columns),
                fill_color='paleturquoise',
                align='left'
            ),
            cells=dict(
                values=[df[col] for col in df.columns],
                fill_color='lavender',
                align='left'
            )
        )])
        
        # Update layout
        fig.update_layout(
            title=title,
            title_x=0.5,
            width=self.default_width,
            height=self.default_height
        )
        
        return fig
    
    def _create_map(
        self, 
        df: pd.DataFrame, 
        lat: Optional[str] = None,
        lon: Optional[str] = None,
        location: Optional[str] = None,
        color: Optional[str] = None,
        size: Optional[str] = None,
        title: str = "Map",
        **kwargs
    ) -> Any:
        """Create a map visualization"""
        # Auto-detect location columns
        if not lat or not lon:
            # Look for common latitude/longitude column names
            lat_names = ['lat', 'latitude', 'Lat', 'Latitude']
            lon_names = ['lon', 'lng', 'longitude', 'Lon', 'Lng', 'Longitude']
            
            # Find latitude column
            if not lat:
                for name in lat_names:
                    if name in df.columns:
                        lat = name
                        break
            
            # Find longitude column
            if not lon:
                for name in lon_names:
                    if name in df.columns:
                        lon = name
                        break
        
        # If we have lat/lon, create scatter mapbox
        if lat and lon:
            # Create figure
            fig = px.scatter_mapbox(
                df,
                lat=lat,
                lon=lon,
                color=color,
                size=size,
                title=title,
                width=self.default_width,
                height=self.default_height,
                **kwargs
            )
            
            # Use open-street-map as default
            fig.update_layout(mapbox_style="open-street-map")
            
        # If no lat/lon but location column (e.g., country names), create choropleth
        elif location:
            # Auto-select a numeric column for color
            if not color:
                for col in df.columns:
                    if pd.api.types.is_numeric_dtype(df[col].dtype) and col != location:
                        color = col
                        break
                
                # If no numeric column found, create a count column
                if not color:
                    df = df.copy()
                    df['count'] = 1
                    color = 'count'
            
            # Create figure
            fig = px.choropleth(
                df,
                locations=location,
                locationmode="country names",
                color=color,
                title=title,
                width=self.default_width,
                height=self.default_height,
                **kwargs
            )
            
        else:
            raise ValueError("Map visualization requires either lat/lon columns or a location column")
        
        # Update layout
        fig.update_layout(
            title_x=0.5,
            template=self.default_theme
        )
        
        return fig
    
    def _create_timeseries(
        self, 
        df: pd.DataFrame, 
        x: Optional[str] = None,
        y: Optional[Union[str, List[str]]] = None,
        title: str = "Time Series",
        **kwargs
    ) -> Any:
        """Create a time series visualization"""
        # Auto-detect date column
        if not x:
            # Look for datetime columns
            for col in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[col].dtype):
                    x = col
                    break
            
            # If no datetime column, try to convert column names that sound like dates
            if not x:
                date_names = ['date', 'time', 'datetime', 'Date', 'Time', 'DateTime']
                for name in date_names:
                    if name in df.columns:
                        try:
                            df[name] = pd.to_datetime(df[name])
                            x = name
                            break
                        except:
                            pass
            
            # If still no date column, use the index if it's a datetime
            if not x and pd.api.types.is_datetime64_any_dtype(df.index):
                df = df.reset_index()
                x = 'index'
            
            if not x:
                raise ValueError("Time series visualization requires a datetime column")
        
        # Auto-select y columns if not provided
        if not y:
            # Use all numeric columns except x
            y = [col for col in df.columns if pd.api.types.is_numeric_dtype(df[col].dtype) and col != x]
            
            # If no numeric columns found, use the second column
            if not y and len(df.columns) > 1:
                y = [df.columns[1]]
        
        # Create figure
        fig = px.line(
            df, 
            x=x, 
            y=y, 
            title=title,
            width=self.default_width,
            height=self.default_height,
            **kwargs
        )
        
        # Update layout
        fig.update_layout(
            title_x=0.5,
            xaxis_title=x,
            yaxis_title=y if isinstance(y, str) else "Value",
            template=self.default_theme
        )
        
        # Add range slider
        fig.update_xaxes(rangeslider_visible=True)
        
        return fig

# Initialize the visualization agent
viz_agent = VisualizationAgent()