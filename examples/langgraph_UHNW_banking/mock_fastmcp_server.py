"""
Mock FastMCP Server for UHNW Private Banking Concierge

This server provides mock tools for processing private banking requests.
Tools are organized into four categories: Portfolio, Market, Tax, and Core Banking.
"""

from fastmcp import FastMCP
from typing import Dict, Any

# Initialize FastMCP server
mcp = FastMCP("UHNW Banking Server")

# Mock data storage
MOCK_PORTFOLIOS = {
    "UHNW-123": {
        "client_id": "UHNW-123",
        "total_aum": 25000000.0,
        "ytd_performance": 18.5,
        "holdings": [
            {"ticker": "NVDA", "shares": 5000, "current_price": 900.0, "total_value": 4500000.0, "percentage": 18.0},
            {"ticker": "MSFT", "shares": 10000, "current_price": 400.0, "total_value": 4000000.0, "percentage": 16.0},
            {"ticker": "GOOGL", "shares": 15000, "current_price": 150.0, "total_value": 2250000.0, "percentage": 9.0},
            {"ticker": "RIVN", "shares": 10000, "current_price": 10.0, "total_value": 100000.0, "percentage": 0.4}
        ]
    }
}

MOCK_UNREALIZED_PL = {
    "UHNW-123": [
        {"ticker": "NVDA", "unrealized_pl": 2500000.0, "pl_percentage": 125.0},
        {"ticker": "MSFT", "unrealized_pl": 1500000.0, "pl_percentage": 60.0},
        {"ticker": "GOOGL", "unrealized_pl": 500000.0, "pl_percentage": 28.5},
        {"ticker": "RIVN", "unrealized_pl": -20000.0, "pl_percentage": -16.6}
    ]
}

MOCK_MARKET_DATA = {
    "NVDA": {"price": 900.0, "pe_ratio": 75.5, "rating": "Strong Buy"},
    "MSFT": {"price": 400.0, "pe_ratio": 35.2, "rating": "Buy"},
    "GOOGL": {"price": 150.0, "pe_ratio": 25.1, "rating": "Buy"},
    "RIVN": {"price": 10.0, "pe_ratio": -2.5, "rating": "Hold"}
}

MOCK_CARDS = {
    "UHNW-123": {
        "8899": {"limit": 150000, "available": 0, "status": "Active"}
    }
}

# ============================================================================
# PORTFOLIO TOOLS (mcp-core-wealth)
# ============================================================================

@mcp.tool()
def get_portfolio_summary(client_id: str) -> Dict[str, Any]:
    """
    Retrieve portfolio summary including holdings, asset allocation, and YTD performance.
    
    Args:
        client_id: The client identifier (e.g., "UHNW-123")
    """
    if client_id in MOCK_PORTFOLIOS:
        return {"success": True, "portfolio": MOCK_PORTFOLIOS[client_id]}
    return {"success": False, "error": f"Portfolio for {client_id} not found"}

@mcp.tool()
def get_unrealized_gains_losses(client_id: str) -> Dict[str, Any]:
    """
    Retrieve open positions and their profit/loss status.
    
    Args:
        client_id: The client identifier (e.g., "UHNW-123")
    """
    if client_id in MOCK_UNREALIZED_PL:
        return {"success": True, "positions": MOCK_UNREALIZED_PL[client_id]}
    return {"success": False, "error": f"P/L data for {client_id} not found"}

# ============================================================================
# MARKET TOOLS (mcp-market-data)
# ============================================================================

@mcp.tool()
def get_live_market_data(ticker: str) -> Dict[str, Any]:
    """
    Fetch real-time price, P/E ratio, and recent analyst ratings.
    
    Args:
        ticker: The stock ticker (e.g., "NVDA")
    """
    ticker = ticker.upper()
    if ticker in MOCK_MARKET_DATA:
        return {"success": True, "data": MOCK_MARKET_DATA[ticker]}
    return {"success": False, "error": f"Market data for {ticker} not found"}

@mcp.tool()
def get_market_news(sector_or_ticker: str) -> Dict[str, Any]:
    """
    Fetch breaking news sentiment for a sector or ticker.
    
    Args:
        sector_or_ticker: Sector name (e.g., "EU AI Regulation") or ticker
    """
    if "EU" in sector_or_ticker.upper() or "AI" in sector_or_ticker.upper():
        return {
            "success": True,
            "sentiment": "Negative Short-term, Neutral Long-term",
            "news": "The EU recently passed the AI Act, which imposes strict compliance on foundation models. Market sentiment indicates this might create headwinds for major US cloud providers operating in Europe."
        }
    return {
        "success": True,
        "sentiment": "Neutral",
        "news": f"Recent developments in {sector_or_ticker} show standard market activity."
    }

@mcp.tool()
def execute_trade(client_id: str, ticker: str, quantity: str, action: str) -> Dict[str, Any]:
    """
    Place a buy or sell order for a stock.
    
    Args:
        client_id: Client identifier
        ticker: Stock ticker
        quantity: Number of shares or "ALL"
        action: "BUY" or "SELL"
    """
    return {
        "success": True,
        "message": f"Successfully executed {action} order for {quantity} shares of {ticker} for client {client_id}."
    }

# ============================================================================
# TAX & COMPLIANCE TOOLS (mcp-risk-tax)
# ============================================================================

@mcp.tool()
def simulate_capital_gains_tax(client_id: str, ticker: str, quantity_to_sell: int) -> Dict[str, Any]:
    """
    Calculate the estimated tax bill for a proposed sale.
    
    Args:
        client_id: Client identifier
        ticker: Stock ticker
        quantity_to_sell: Number of shares to sell
    """
    if ticker.upper() == "NVDA":
        return {
            "success": True,
            "estimated_tax": 45000.0,
            "tax_type": "Long-term Capital Gains",
            "message": f"Selling {quantity_to_sell} shares of NVDA will trigger an estimated $45,000 in long-term capital gains tax."
        }
    return {"success": True, "estimated_tax": 0.0, "message": "No significant tax implications calculated."}

@mcp.tool()
def get_tax_loss_harvesting_options(client_id: str) -> Dict[str, Any]:
    """
    Recommend losing positions to sell to offset gains.
    
    Args:
        client_id: Client identifier
    """
    return {
        "success": True,
        "recommendations": [
            {
                "ticker": "RIVN",
                "unrealized_loss": -20000.0,
                "suggestion": "We could sell your RIVN position to offset nearly half of the NVDA tax hit."
            }
        ]
    }

@mcp.tool()
def run_aml_transaction_check(client_id: str, amount: float, destination: str) -> Dict[str, Any]:
    """
    Run an Anti-Money Laundering check for large outbound wires.
    
    Args:
        client_id: Client identifier
        amount: Wire amount
        destination: Recipient name/organization
    """
    if amount > 1000000:
        return {
            "success": True,
            "cleared_ofac": True,
            "requires_confirmation": True,
            "message": f"AML screening passed for {destination}. Amount exceeds $1M, requiring quick verbal or SMS confirmation."
        }
    return {"success": True, "cleared_ofac": True, "requires_confirmation": False}

# ============================================================================
# CORE BANKING TOOLS (mcp-core-banking)
# ============================================================================

@mcp.tool()
def update_card_limit(client_id: str, card_last_4: str, new_limit: float) -> Dict[str, Any]:
    """
    Temporarily raises credit/spending limits.
    
    Args:
        client_id: Client identifier
        card_last_4: Last 4 digits of the card
        new_limit: Requested new limit amount
    """
    return {
        "success": True,
        "card_last_4": card_last_4,
        "new_limit": new_limit,
        "message": f"Successfully raised card limit to ${new_limit:,.2f}."
    }

@mcp.tool()
def initiate_wire_transfer(client_id: str, amount: float, recipient: str) -> Dict[str, Any]:
    """
    Wires money to external accounts.
    
    Args:
        client_id: Client identifier
        amount: Wire amount
        recipient: Recipient name/organization
    """
    return {
        "success": True,
        "amount": amount,
        "recipient": recipient,
        "status": "Initiated",
        "message": f"Wire transfer of ${amount:,.2f} to {recipient} has been successfully initiated."
    }

if __name__ == "__main__":
    print("=" * 60)
    print("Mock FastMCP Server - UHNW Private Banking")
    print("=" * 60)
    mcp.run()
