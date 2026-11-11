def calculate_invoice(subtotal, tax_rate, discount=0):
    tax = subtotal * tax_rate
    return subtotal + tax + discount
