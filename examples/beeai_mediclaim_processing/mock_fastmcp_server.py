"""
Mock FastMCP Server for Mediclaim Processing

This server provides 6 mock tools for processing post-hospitalization medical insurance claims.
Tools are organized into three categories: Policy, Billing, and Claim Processing.
"""

from fastmcp import FastMCP
from typing import Dict, Any

# Initialize FastMCP server
mcp = FastMCP("Mediclaim Processing Server")

# Mock data storage
MOCK_POLICIES = {
    "POL-999": {
        "policy_number": "POL-999",
        "policy_holder": "John Doe",
        "coverage_type": "Comprehensive Health",
        "annual_limit": 500000,
        "co_pay_percentage": 10,
        "active": True
    }
}

MOCK_COVERAGE = {
    "POL-999": {
        "knee_replacement": {"covered": True, "limit": 300000},
        "cardiac_surgery": {"covered": True, "limit": 400000},
        "dental": {"covered": False, "limit": 0}
    }
}

MOCK_PATIENTS = {
    "1024": {
        "patient_id": "1024",
        "name": "John Doe",
        "age": 58,
        "policy_number": "POL-999",
        "admission_date": "2024-01-15",
        "discharge_date": "2024-01-22",
        "diagnosis": "Knee Replacement Surgery",
        "hospital": "City General Hospital"
    }
}

MOCK_BILLS = {
    "1024": {
        "patient_id": "1024",
        "total_bill": 285000,
        "surgery_cost": 200000,
        "room_charges": 50000,
        "medicines": 25000,
        "diagnostics": 10000,
        "verified": True,
        "verification_date": "2024-01-23"
    }
}


# ============================================================================
# POLICY TOOLS
# ============================================================================

@mcp.tool()
def get_policy_details(policy_number: str) -> Dict[str, Any]:
    """
    Retrieve insurance policy details for a given policy number.
    
    Args:
        policy_number: The policy number to look up (e.g., "POL-999")
    
    Returns:
        Dictionary containing policy details including coverage type, limits, and status
    """
    if policy_number in MOCK_POLICIES:
        return {
            "success": True,
            "policy": MOCK_POLICIES[policy_number]
        }
    else:
        return {
            "success": False,
            "error": f"Policy {policy_number} not found"
        }


@mcp.tool()
def check_coverage_limits(policy_number: str, treatment_type: str) -> Dict[str, Any]:
    """
    Check if a specific treatment type is covered and retrieve coverage limits.
    
    Args:
        policy_number: The policy number (e.g., "POL-999")
        treatment_type: Type of treatment (e.g., "knee_replacement", "cardiac_surgery")
    
    Returns:
        Dictionary with coverage status and limit amount
    """
    if policy_number not in MOCK_COVERAGE:
        return {
            "success": False,
            "error": f"Policy {policy_number} not found"
        }
    
    coverage = MOCK_COVERAGE[policy_number]
    treatment_key = treatment_type.lower().replace(" ", "_")
    
    if treatment_key in coverage:
        return {
            "success": True,
            "policy_number": policy_number,
            "treatment_type": treatment_type,
            "covered": coverage[treatment_key]["covered"],
            "coverage_limit": coverage[treatment_key]["limit"]
        }
    else:
        return {
            "success": True,
            "policy_number": policy_number,
            "treatment_type": treatment_type,
            "covered": False,
            "coverage_limit": 0,
            "message": "Treatment type not explicitly listed in policy"
        }


# ============================================================================
# BILLING TOOLS
# ============================================================================

@mcp.tool()
def fetch_discharge_summary(patient_id: str) -> Dict[str, Any]:
    """
    Fetch the hospital discharge summary for a patient.
    
    Args:
        patient_id: The patient ID (e.g., "1024")
    
    Returns:
        Dictionary containing patient details, diagnosis, and hospitalization dates
    """
    if patient_id in MOCK_PATIENTS:
        return {
            "success": True,
            "discharge_summary": MOCK_PATIENTS[patient_id]
        }
    else:
        return {
            "success": False,
            "error": f"Patient {patient_id} not found"
        }


@mcp.tool()
def verify_hospital_bills(patient_id: str) -> Dict[str, Any]:
    """
    Verify and retrieve itemized hospital bills for a patient.
    
    Args:
        patient_id: The patient ID (e.g., "1024")
    
    Returns:
        Dictionary with verified bill details including total and itemized costs
    """
    if patient_id in MOCK_BILLS:
        return {
            "success": True,
            "bill_details": MOCK_BILLS[patient_id]
        }
    else:
        return {
            "success": False,
            "error": f"Bills for patient {patient_id} not found"
        }


# ============================================================================
# CLAIM PROCESSING TOOLS
# ============================================================================

@mcp.tool()
def calculate_claimable_amount(
    total_bill_amount: float,
    coverage_limit: float,
    co_pay_percentage: float
) -> Dict[str, Any]:
    """
    Calculate the final claimable amount after applying coverage limits and co-pay.
    
    Args:
        total_bill_amount: Total hospital bill amount
        coverage_limit: Maximum coverage limit for the treatment
        co_pay_percentage: Co-payment percentage (e.g., 10 for 10%)
    
    Returns:
        Dictionary with calculation breakdown and final claimable amount
    """
    # Apply coverage limit
    covered_amount = min(total_bill_amount, coverage_limit)
    
    # Calculate co-pay
    co_pay_amount = covered_amount * (co_pay_percentage / 100)
    
    # Final claimable amount
    claimable_amount = covered_amount - co_pay_amount
    
    return {
        "success": True,
        "calculation": {
            "total_bill": total_bill_amount,
            "coverage_limit": coverage_limit,
            "covered_amount": covered_amount,
            "co_pay_percentage": co_pay_percentage,
            "co_pay_amount": co_pay_amount,
            "final_claimable_amount": claimable_amount
        }
    }


@mcp.tool()
def submit_mediclaim(
    policy_number: str,
    patient_id: str,
    claim_amount: float
) -> Dict[str, Any]:
    """
    Submit the final mediclaim for processing.
    
    Args:
        policy_number: The policy number (e.g., "POL-999")
        patient_id: The patient ID (e.g., "1024")
        claim_amount: The final claimable amount
    
    Returns:
        Dictionary with claim submission confirmation and reference number
    """
    import random
    import datetime
    
    # Generate claim reference number
    claim_ref = f"CLM-{random.randint(100000, 999999)}"
    
    return {
        "success": True,
        "claim_submission": {
            "claim_reference": claim_ref,
            "policy_number": policy_number,
            "patient_id": patient_id,
            "claim_amount": claim_amount,
            "submission_date": datetime.datetime.now().isoformat(),
            "status": "Submitted",
            "estimated_processing_days": 7,
            "message": "Claim submitted successfully. You will receive updates via email."
        }
    }


# ============================================================================
# SERVER STARTUP
# ============================================================================

if __name__ == "__main__":
    # Run the FastMCP server
    print("=" * 60)
    print("Mock FastMCP Server - Mediclaim Processing")
    print("=" * 60)
    print("\nAvailable Tools:")
    print("  Policy Tools:")
    print("    - get_policy_details")
    print("    - check_coverage_limits")
    print("  Billing Tools:")
    print("    - fetch_discharge_summary")
    print("    - verify_hospital_bills")
    print("  Claim Processing Tools:")
    print("    - calculate_claimable_amount")
    print("    - submit_mediclaim")
    print("\n" + "=" * 60)
    print("Server starting...")
    print("=" * 60 + "\n")
    
    mcp.run()

# Made with Bob
