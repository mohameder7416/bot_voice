import os
import json
import requests
from .utils import create_pwa_log, create_token
from bot.variables.variables import load_variables

async def make_appointment_handler():
    """Generate a link for a customer to book an appointment with available time slots"""
    try:
        variables = load_variables()
        lead_id_crm = variables["lead_crm_id"]
        
        url = f"{os.getenv('PWA_API_CRM', '')}/appointment/link"
        payload = json.dumps({
            "lead_id": int(lead_id_crm),
            "source": "AI Bot"
        })
        
        headers = create_token()
        response = requests.request("GET", url, headers=headers, data=payload)
        
        if response.ok:
            result = response.json().get('result', '')
            return f"Here's your appointment booking link: {result}"
        else:
            return "I'm sorry, I couldn't generate an appointment link at this time."
    except Exception as e:
        create_pwa_log(f"Error in make_appointment: {str(e)}")
        return "I'm sorry, I encountered an error while trying to generate an appointment link."

