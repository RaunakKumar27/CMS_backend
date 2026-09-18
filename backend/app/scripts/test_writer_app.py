import asyncio
import os
import io
import time
import httpx
from datetime import datetime

async def run_writer_application_tests():
    print("[TEST] Running DO Record Writer Registration & Photo Upload Integration Tests...")
    
    base_url = "http://127.0.0.1:8000"
    ts = int(time.time())
    test_email = f"applicant_test_{ts}@dorecord.com"
    
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        
        # 1. Public Become a Writer page
        r_page = await client.get("/become-a-writer")
        print(f"1. GET /become-a-writer -> Status {r_page.status_code}")
        assert r_page.status_code == 200
        assert "Become a DO Record Writer" in r_page.text
        
        # Create a dummy image file buffer for photo upload test
        dummy_img_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
        files = {
            "photo_file": ("test_avatar.png", io.BytesIO(dummy_img_bytes), "image/png")
        }
        data = {
            "full_name": f"Test Journalist Applicant {ts}",
            "email": test_email,
            "phone": "+91 99999 88888",
            "city": "Bengaluru",
            "country": "India",
            "bio": "Experienced investigative tech reporter specializing in AI policy and semiconductors.",
            "areas_of_interest": "Technology & AI",
            "writing_experience": "Written 50+ articles for Tech Daily News.",
            "portfolio_url": "https://example.com/portfolio",
            "linkedin_url": "https://linkedin.com/in/testapplicant",
            "password": "Applicant@123456",
            "confirm_password": "Applicant@123456"
        }
        
        # 2. Submit Writer Application with Photo Upload
        r_submit = await client.post("/become-a-writer", data=data, files=files)
        print(f"2. POST /become-a-writer (with Photo Upload) -> Status {r_submit.status_code}")
        assert r_submit.status_code == 200
        assert "Application Submitted Successfully" in r_submit.text
        
        # 3. Unapproved applicant tries to log in
        r_login_pending = await client.post("/login", data={"identity": test_email, "password": "Applicant@123456"}, follow_redirects=False)
        print(f"3. Pending Applicant Login Attempt -> Status {r_login_pending.status_code} (Blocked with Alert)")
        assert r_login_pending.status_code == 403
        assert "currently under review" in r_login_pending.text
        
        # 4. Super Admin Login
        r_admin_login = await client.post("/login", data={"identity": "admin@dorecord.com", "password": "Admin@123456"}, follow_redirects=False)
        admin_cookies = r_admin_login.cookies
        print(f"4. Super Admin Login -> Status {r_admin_login.status_code}")
        assert r_admin_login.status_code == 303
        
        # 5. Super Admin List Applications
        r_apps_list = await client.get("/admin/writer-applications", cookies=admin_cookies)
        print(f"5. GET /admin/writer-applications -> Status {r_apps_list.status_code}")
        assert r_apps_list.status_code == 200
        assert f"Test Journalist Applicant {ts}" in r_apps_list.text
        
        # Extract Application ID from DB
        from app.core.database import writer_applications_collection, activation_tokens_collection
        app_doc = await writer_applications_collection.find_one({"email": test_email})
        assert app_doc is not None
        app_id = str(app_doc["_id"])
        
        # 6. View Application Detail Page
        r_app_detail = await client.get(f"/admin/writer-applications/{app_id}", cookies=admin_cookies)
        print(f"6. GET /admin/writer-applications/{app_id} -> Status {r_app_detail.status_code}")
        assert r_app_detail.status_code == 200
        assert "Uploaded Profile Photo" in r_app_detail.text
        
        # 7. Super Admin Approves Application
        r_approve = await client.post(
            f"/admin/writer-applications/{app_id}/approve",
            data={"admin_notes": "Verified technology portfolio and headshot."},
            cookies=admin_cookies,
            follow_redirects=False
        )
        print(f"7. POST /admin/writer-applications/{app_id}/approve -> Status {r_approve.status_code}")
        assert r_approve.status_code == 303
        
        # Verify activation token created
        token_doc = await activation_tokens_collection.find_one({"application_id": app_id, "used": False})
        assert token_doc is not None
        act_token = token_doc["token"]
        
        # 8. Access Account Activation Page
        r_act_page = await client.get(f"/activate-account?token={act_token}")
        print(f"8. GET /activate-account?token={act_token} -> Status {r_act_page.status_code}")
        assert r_act_page.status_code == 200
        assert "Activate Writer Account" in r_act_page.text
        
        # 9. Complete Account Activation & Login as Approved Writer
        r_writer_login = await client.post("/login", data={"identity": test_email, "password": "Applicant@123456"}, follow_redirects=False)
        writer_cookies = r_writer_login.cookies
        print(f"9. Approved Writer Login -> Status {r_writer_login.status_code}")
        assert r_writer_login.status_code == 303
        
        # 10. Access Writer Dashboard
        r_writer_dash = await client.get("/writer", cookies=writer_cookies)
        print(f"10. GET /writer Dashboard -> Status {r_writer_dash.status_code}")
        assert r_writer_dash.status_code == 200
        
        # 11. Update Profile Photo via Writer Profile
        new_avatar_files = {
            "photo_file": ("new_writer_headshot.png", io.BytesIO(dummy_img_bytes), "image/png")
        }
        r_update_photo = await client.post("/writer/profile/upload-photo", files=new_avatar_files, cookies=writer_cookies, follow_redirects=False)
        print(f"11. POST /writer/profile/upload-photo -> Status {r_update_photo.status_code}")
        assert r_update_photo.status_code == 303

        print("\n[SUCCESS] ALL 11 WRITER REGISTRATION & PHOTO UPLOAD TESTS PASSED PERFECTLY!")

if __name__ == "__main__":
    asyncio.run(run_writer_application_tests())
