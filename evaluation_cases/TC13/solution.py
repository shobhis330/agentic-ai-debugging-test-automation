def validate_user_payload(payload):
    return "name" in payload and "email" in payload
