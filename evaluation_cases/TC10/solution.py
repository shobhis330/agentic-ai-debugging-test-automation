def calculate_retry_delay(attempt, base=2, maximum=30):
    return min(base * (2 ** (attempt - 1)), maximum)
