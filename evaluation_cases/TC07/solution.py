def paginate(items, page, page_size):
    start = page * page_size
    return items[start:start + page_size]
