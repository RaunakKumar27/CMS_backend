import asyncio
import httpx

async def test_live_server():
    print("[TEST] Testing live server endpoints at http://127.0.0.1:8000...")
    
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000") as client:
        # 1. Health check
        r_health = await client.get("/health")
        print(f"1. GET /health -> Status {r_health.status_code}, Response: {r_health.json()}")
        assert r_health.status_code == 200
        assert r_health.json().get("status") == "ok"
        assert r_health.json().get("service") == "DO Record CMS API"
        
        # 2. Root Endpoint (API JSON Accept)
        r_root_json = await client.get("/", headers={"accept": "application/json"})
        print(f"2. GET / (JSON) -> Status {r_root_json.status_code}, Response: {r_root_json.json()}")
        assert r_root_json.status_code == 200
        assert r_root_json.json().get("status") == "ok"
        
        # 3. Root Endpoint (HTML Browser Accept)
        r_root_html = await client.get("/", headers={"accept": "text/html"})
        print(f"3. GET / (HTML) -> Status {r_root_html.status_code}")
        assert r_root_html.status_code == 200
        assert "DO" in r_root_html.text and "RECORD" in r_root_html.text
        
        # 4. Swagger UI Docs
        r_docs = await client.get("/docs")
        print(f"4. GET /docs -> Status {r_docs.status_code} (Swagger UI Loaded)")
        assert r_docs.status_code == 200
        assert "swagger-ui" in r_docs.text.lower()
        
        # 5. API Auth Login
        r_login_api = await client.post("/api/auth/login", json={"identity": "admin@dorecord.com", "password": "Admin@123456"})
        print(f"5. POST /api/auth/login -> Status {r_login_api.status_code}")
        assert r_login_api.status_code == 200
        assert "access_token" in r_login_api.json()
        token = r_login_api.json()["access_token"]
        
        # 6. API Auth Me
        r_me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        print(f"6. GET /api/auth/me -> Status {r_me.status_code}, User: {r_me.json().get('username')}")
        assert r_me.status_code == 200
        assert r_me.json().get("role") == "super_admin"
        
        # 7. Web Form Admin Login
        r_web_login = await client.post("/login", data={"identity": "admin@dorecord.com", "password": "Admin@123456"}, follow_redirects=False)
        print(f"7. POST /login -> Status {r_web_login.status_code}")
        assert r_web_login.status_code == 303
        admin_cookies = r_web_login.cookies
        
        # 8. Protected Super Admin Route
        r_admin_dash = await client.get("/admin", cookies=admin_cookies)
        print(f"8. GET /admin -> Status {r_admin_dash.status_code}")
        assert r_admin_dash.status_code == 200
        
        # 9. Writer Login & RBAC Violation Attempt
        r_w_login = await client.post("/login", data={"identity": "rohit@dorecord.com", "password": "Writer@123456"}, follow_redirects=False)
        writer_cookies = r_w_login.cookies
        r_forbidden = await client.get("/admin/settings", cookies=writer_cookies)
        print(f"9. Writer access to /admin/settings -> Status {r_forbidden.status_code} (HTTP 403 Forbidden)")
        assert r_forbidden.status_code == 403

        print("\n[SUCCESS] ALL LIVE SERVER API & AUTH TESTS PASSED PERFECTLY!")

if __name__ == "__main__":
    asyncio.run(test_live_server())
