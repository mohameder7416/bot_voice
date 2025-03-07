import json
import os

class Variables:
    def __init__(self):
        self.dealer_id = None
        self.lead_id = None
        self.lead_crm_id = None
        self.product_id = None

variables = Variables()

# Path to the variables.json file
VARIABLES_FILE = os.path.join(os.path.dirname(__file__), 'variables.json')

def load_variables():
    if os.path.exists(VARIABLES_FILE):
        with open(VARIABLES_FILE, 'r') as f:
            return json.load(f)
    return {"lead_id": 1, "dealer_id": 1, "lead_crm_id": 1, "product_id": 1}

def save_variables(vars):
    with open(VARIABLES_FILE, 'w') as f:
        json.dump(vars, f)

# Initialize variables from file
initial_vars = load_variables()
variables.dealer_id = initial_vars["dealer_id"]
variables.lead_id = initial_vars["lead_id"]
variables.lead_crm_id = initial_vars["lead_crm_id"]
variables.product_id = initial_vars["product_id"]

