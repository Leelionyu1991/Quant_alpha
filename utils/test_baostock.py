import baostock as bs, threading, time

result = {}
def fetch():
    global result
    bs.login()
    rs = bs.query_all_stock(day='')
    stocks = []
    while rs.next(): stocks.append(rs.get_row_data())
    result = {'stocks': stocks, 'fields': rs.fields, 'logged_in': True}
    bs.logout()

t = threading.Thread(target=fetch)
t.daemon = True
t.start()
t.join(timeout=10)

if t.is_alive():
    print('TIMEOUT - baostock query hanging after 10s')
    print('Will try Tencent Finance directly...')
else:
    print(f"Got {len(result.get('stocks', []))} stocks, fields: {result.get('fields', [])}")
