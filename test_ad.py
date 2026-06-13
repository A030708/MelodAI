import app, recommender
recommender.init_app()
from auth import init_db
init_db()

with app.app.test_client() as c:
    with c.session_transaction() as sess:
        sess['user_id'] = 3
        sess['username'] = 'shanthaa'
        sess['role'] = 'artist'
    r = c.get('/artist/announce')
    print('Announce status:', r.status_code)
    if r.status_code != 200:
        print('Redirect:', r.location if hasattr(r, 'location') else 'N/A')
        print('Body:', r.get_data(as_text=True)[:300])
    else:
        html = r.get_data(as_text=True)
        print('Has Send button:', 'Send Announcement' in html)
        print('Has title input:', 'name="title"' in html)
        print('Has textarea:', 'name="message"' in html)
    
    r2 = c.get('/artist/dashboard')
    print('Dashboard status:', r2.status_code)
    if r2.status_code != 200:
        print('Body[:300]:', r2.get_data(as_text=True)[:300])
