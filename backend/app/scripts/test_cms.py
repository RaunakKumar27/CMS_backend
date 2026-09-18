import asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app

async def run_cms_tests():
    print("[TEST] Running DO Record CMS Integration Tests...")
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Public Homepage
        r1 = await client.get("/")
        print(f"1. Public Homepage GET / -> Status {r1.status_code}")
        assert r1.status_code == 200
        assert "DO" in r1.text and "RECORD" in r1.text
        
        # 2. Article Detail
        r2 = await client.get("/article/india-unveils-next-gen-ai-computing-grid-infrastructure-project")
        print(f"2. Article Detail GET /article/... -> Status {r2.status_code}")
        assert r2.status_code == 200
        assert "Compute Capabilities" in r2.text
        
        # 3. Trending Page
        r3 = await client.get("/trending")
        print(f"3. Trending GET /trending -> Status {r3.status_code}")
        assert r3.status_code == 200
        
        # 4. Search Page
        r4 = await client.get("/search?q=AI")
        print(f"4. Search GET /search?q=AI -> Status {r4.status_code}")
        assert r4.status_code == 200
        
        # 5. Category Page
        r5 = await client.get("/category/technology")
        print(f"5. Category GET /category/technology -> Status {r5.status_code}")
        assert r5.status_code == 200
        
        # 6. Auth Protection: Unauthenticated access to /admin
        r6 = await client.get("/admin", follow_redirects=False)
        print(f"6. Unauthenticated GET /admin -> Status {r6.status_code} (Redirects to login)")
        assert r6.status_code in [302, 307]
        assert "/login" in r6.headers.get("location", "")
        
        # 7. Super Admin Login
        login_data = {"identity": "admin@dorecord.com", "password": "Admin@123456", "remember_me": "false", "next": ""}
        r7 = await client.post("/login", data=login_data, follow_redirects=False)
        print(f"7. Admin Login POST /login -> Status {r7.status_code}")
        assert r7.status_code == 303
        assert "access_token" in r7.cookies
        admin_cookies = r7.cookies
        
        # 8. Super Admin Dashboard with Session Cookie
        r8 = await client.get("/admin", cookies=admin_cookies)
        print(f"8. Super Admin Dashboard GET /admin -> Status {r8.status_code}")
        assert r8.status_code == 200
        assert "Newsroom Operations Control Center" in r8.text
        
        # 9. Super Admin Articles List
        r9 = await client.get("/admin/articles", cookies=admin_cookies)
        print(f"9. Super Admin Articles List GET /admin/articles -> Status {r9.status_code}")
        assert r9.status_code == 200
        
        # 10. Writer Login
        writer_login = {"identity": "rohit@dorecord.com", "password": "Writer@123456", "remember_me": "false", "next": ""}
        r10 = await client.post("/login", data=writer_login, follow_redirects=False)
        print(f"10. Writer Login POST /login -> Status {r10.status_code}")
        assert r10.status_code == 303
        writer_cookies = r10.cookies
        
        # 11. Writer Dashboard
        r11 = await client.get("/writer", cookies=writer_cookies)
        print(f"11. Writer Dashboard GET /writer -> Status {r11.status_code}")
        assert r11.status_code == 200
        assert "Welcome back" in r11.text
        
        # 12. Security Test: Writer forbidden from accessing /admin/settings
        r12 = await client.get("/admin/settings", cookies=writer_cookies)
        print(f"12. Writer Access to /admin/settings -> Status {r12.status_code} (HTTP 403 Forbidden)")
        assert r12.status_code == 403
        
        print("\n[SUCCESS] ALL 12 INTEGRATION & SECURITY TESTS PASSED PERFECTLY!")

if __name__ == "__main__":
    asyncio.run(run_cms_tests())

