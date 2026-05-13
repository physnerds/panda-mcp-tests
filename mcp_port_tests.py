import argparse
import requests
import json

def main():
    parser = argparse.ArgumentParser(description='Test MCP client')
    parser.add_argument('--tool', required=True, help='Tool name to call (e.g., is_alive)')
    parser.add_argument('--host', default='localhost', help='MCP server host')
    parser.add_argument('--port', type=int, default=25888, help='MCP server port')
    parser.add_argument('--use_http', action='store_true', help='Use HTTP instead of HTTPS')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    parser.add_argument('--params', type=str, help='JSON string of parameters')
    
    args = parser.parse_args()
    
    # Construct URL
    protocol = 'http' if args.use_http else 'https'
    url = f"{protocol}://{args.host}:{args.port}/mcp"
    
    # Parse parameters
    params = {}
    if args.params:
        try:
            params = json.loads(args.params)
        except json.JSONDecodeError as e:
            print(f"Error parsing params: {e}")
            return
    
    # Construct request payload
    payload = {
        "jsonrpc": "2.0",
        "method": args.tool,
        "params": params,
        "id": 1
    }
    
    if args.verbose:
        print(f"=== Request Details ===")
        print(f"URL: {url}")
        print(f"Method: POST")
        print(f"Headers: {{'Content-Type': 'application/json'}}")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        print()
    
    try:
        response = requests.post(
            url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=10,
            verify=False if args.use_http else True
        )
        
        if args.verbose:
            print(f"=== Response Details ===")
            print(f"Status Code: {response.status_code}")
            print(f"Headers: {dict(response.headers)}")
            print()
        
        print(f"=== Response Body ===")
        try:
            print(json.dumps(response.json(), indent=2))
        except json.JSONDecodeError:
            print(response.text)
            
    except requests.exceptions.ConnectionError as e:
        print(f"Connection Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
    except requests.exceptions.Timeout:
        print(f"Request timed out")
    except Exception as e:
        print(f"Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    main()