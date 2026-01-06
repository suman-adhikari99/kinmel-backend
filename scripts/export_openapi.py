#!/usr/bin/env python3
"""
OpenAPI Schema Export Script
============================
Exports the OpenAPI schema to JSON and optionally generates static documentation.

Usage:
    python scripts/export_openapi.py                    # Export to docs/openapi.json
    python scripts/export_openapi.py -o api-spec.json   # Custom output file
    python scripts/export_openapi.py --yaml             # Export as YAML
    python scripts/export_openapi.py --html             # Generate HTML docs (Redoc)

Output:
- JSON/YAML schema file for API consumers
- Optional HTML documentation for static hosting
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def export_openapi(
    output_path: str = "docs/openapi.json",
    format: str = "json",
    generate_html: bool = False,
) -> None:
    """
    Export OpenAPI schema from the FastAPI application.
    
    Args:
        output_path: Path to output file
        format: Output format ('json' or 'yaml')
        generate_html: Also generate HTML documentation
    """
    # Import app to get schema
    from src.main import app
    
    # Get OpenAPI schema
    openapi_schema = app.openapi()
    
    # Ensure output directory exists
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Export schema
    if format == "yaml":
        try:
            import yaml
            with open(output_file, "w") as f:
                yaml.dump(openapi_schema, f, default_flow_style=False, sort_keys=False)
        except ImportError:
            print("❌ PyYAML not installed. Run: pip install pyyaml")
            print("   Falling back to JSON...")
            format = "json"
            output_file = output_file.with_suffix(".json")
    
    if format == "json":
        with open(output_file, "w") as f:
            json.dump(openapi_schema, f, indent=2, default=str)
    
    print(f"✅ OpenAPI schema exported to: {output_file}")
    print(f"   Format: {format.upper()}")
    print(f"   Title: {openapi_schema['info']['title']}")
    print(f"   Version: {openapi_schema['info']['version']}")
    print(f"   Paths: {len(openapi_schema['paths'])}")
    
    # Generate HTML documentation if requested
    if generate_html:
        generate_html_docs(openapi_schema, output_file.parent)


def generate_html_docs(schema: dict, output_dir: Path) -> None:
    """
    Generate static HTML documentation using Redoc.
    
    Creates a single HTML file that loads the OpenAPI spec
    and renders it with Redoc.
    """
    html_file = output_dir / "index.html"
    
    # Inline the OpenAPI spec into the HTML
    spec_json = json.dumps(schema, indent=2, default=str)
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{schema['info']['title']} - API Documentation</title>
    <meta name="description" content="{schema['info'].get('description', '')[:150]}">
    
    <!-- Redoc CSS -->
    <link href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700" rel="stylesheet">
    <style>
        body {{
            margin: 0;
            padding: 0;
        }}
    </style>
</head>
<body>
    <div id="redoc-container"></div>
    
    <!-- Redoc -->
    <script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>
    
    <script>
        // Inline OpenAPI spec
        const spec = {spec_json};
        
        // Initialize Redoc
        Redoc.init(spec, {{
            scrollYOffset: 0,
            hideHostname: false,
            expandResponses: "200,201",
            requiredPropsFirst: true,
            sortPropsAlphabetically: true,
            pathInMiddlePanel: true,
            hideDownloadButton: false,
            theme: {{
                colors: {{
                    primary: {{
                        main: '#2563eb'
                    }}
                }},
                typography: {{
                    fontSize: '15px',
                    fontFamily: '"Roboto", sans-serif',
                    headings: {{
                        fontFamily: '"Montserrat", sans-serif',
                    }}
                }},
                sidebar: {{
                    backgroundColor: '#fafafa',
                    width: '260px'
                }}
            }}
        }}, document.getElementById('redoc-container'));
    </script>
</body>
</html>
"""
    
    with open(html_file, "w") as f:
        f.write(html_content)
    
    print(f"✅ HTML documentation generated: {html_file}")
    print(f"   Open in browser or serve statically")


def generate_swagger_html(schema: dict, output_dir: Path) -> None:
    """
    Generate static HTML documentation using Swagger UI.
    
    Alternative to Redoc with interactive "Try it out" feature.
    """
    html_file = output_dir / "swagger.html"
    
    spec_json = json.dumps(schema, indent=2, default=str)
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{schema['info']['title']} - Swagger UI</title>
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
    <style>
        html {{ box-sizing: border-box; overflow-y: scroll; }}
        *, *:before, *:after {{ box-sizing: inherit; }}
        body {{ margin: 0; background: #fafafa; }}
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    
    <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
        const spec = {spec_json};
        
        window.onload = function() {{
            SwaggerUIBundle({{
                spec: spec,
                dom_id: '#swagger-ui',
                deepLinking: true,
                presets: [
                    SwaggerUIBundle.presets.apis,
                    SwaggerUIBundle.SwaggerUIStandalonePreset
                ],
                layout: "StandaloneLayout",
                persistAuthorization: true,
                filter: true,
                tagsSorter: 'alpha',
                operationsSorter: 'alpha',
            }});
        }};
    </script>
</body>
</html>
"""
    
    with open(html_file, "w") as f:
        f.write(html_content)
    
    print(f"✅ Swagger UI generated: {html_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Export OpenAPI schema and generate documentation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/export_openapi.py                     # Export JSON
    python scripts/export_openapi.py -o api.yaml --yaml  # Export YAML
    python scripts/export_openapi.py --html              # With HTML docs
    python scripts/export_openapi.py --swagger           # With Swagger UI
        """,
    )
    
    parser.add_argument(
        "-o", "--output",
        default="docs/openapi.json",
        help="Output file path (default: docs/openapi.json)",
    )
    
    parser.add_argument(
        "--yaml",
        action="store_true",
        help="Export as YAML instead of JSON",
    )
    
    parser.add_argument(
        "--html",
        action="store_true",
        help="Generate HTML documentation (Redoc)",
    )
    
    parser.add_argument(
        "--swagger",
        action="store_true",
        help="Generate Swagger UI HTML",
    )
    
    args = parser.parse_args()
    
    # Determine format
    format = "yaml" if args.yaml else "json"
    
    # Export schema
    export_openapi(
        output_path=args.output,
        format=format,
        generate_html=args.html,
    )
    
    # Generate Swagger UI if requested
    if args.swagger:
        from src.main import app
        output_dir = Path(args.output).parent
        generate_swagger_html(app.openapi(), output_dir)
    
    print("\n📘 Documentation Tips:")
    print("   - Serve /docs on your FastAPI app for interactive docs")
    print("   - Use /redoc for cleaner read-only documentation")
    print("   - Share openapi.json with API consumers")
    print("   - Import into Postman, Insomnia, or other tools")


if __name__ == "__main__":
    main()
