import json
import time
import os
import sys

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def format_value(val, fmt="{:.2f}"):
    if val is None: return "N/A"
    return fmt.format(val)

def view_dashboard():
    path = "aevara/state/dashboard.json"
    
    print("Connecting to AEVRA Cognitive Stream...")
    
    while True:
        try:
            if not os.path.exists(path):
                time.sleep(1)
                continue
                
            with open(path, "r") as f:
                data = json.load(f)
            
            clear_screen()
            
            health_color = "🟢" if data.get("system_health_score", 0) > 80 else "🟡" if data.get("system_health_score", 0) > 50 else "🔴"
            sharpe_status = "✅" if data.get("rolling_sharpe_50", 0) > 1.2 else "⚠️" if data.get("rolling_sharpe_50", 0) > 0.5 else "❌"
            edge_status = "YES 🔴" if data.get("edge_decay_detected") else "NO ✅"
            
            print("══════════════════════════════════════════════════════════")
            print(f" AEVRA TERMINAL DASHBOARD [{data.get('phase', 'DEMO')}]")
            print(f" Updated: {data.get('published_at', 'unknown')}")
            print("══════════════════════════════════════════════════════════")
            print(f" Regime: {data.get('regime', 'N/A')} ")
            print(f" Ensemble Confidence: {format_value(data.get('ensemble_confidence'))} ")
            print(f" Rolling Sharpe (50): {format_value(data.get('rolling_sharpe_50'))} {sharpe_status}")
            print(f" Edge Decay Detected: {edge_status}")
            print("──────────────────────────────────────────────────────────")
            print(f" Active Positions: {data.get('active_positions', 0)}")
            print(f" Daily P&L (USD): ${format_value(data.get('daily_pnl_usd'))}")
            print(f" FTMO Daily Buffer: {format_value(data.get('ftmo_daily_dd_pct'))}% / 4.00%")
            print(f" FTMO Total Buffer: {format_value(data.get('ftmo_total_dd_pct'))}% / 8.00%")
            print("──────────────────────────────────────────────────────────")
            print(f" System Health: {data.get('system_health_score', 0):.0f}/100 {health_color}")
            print("══════════════════════════════════════════════════════════")
            
            time.sleep(2)
        except KeyboardInterrupt:
            print("\nExiting Viewer.")
            break
        except Exception as e:
            print(f"Error reading dashboard: {e}")
            time.sleep(2)

if __name__ == "__main__":
    view_dashboard()
