# Content Management System (CMS) Backend

A small, production-style **Content Management System (CMS) backend** built using **FastAPI**, **MongoDB**, and **Jinja2**.  
This project allows users to **create, read, update, delete**, and **render content as HTML pages** through API endpoints.

## Features

 Create content items (title, body, author, tags, template)
 Retrieve single or all content items
 Update existing content
 Delete content
 Render content as a real **HTML webpage**
 MongoDB for data storage
 FastAPI with OpenAPI (Swagger UI)
 Clean modular backend structure

##  Tech Stack

- **Backend Framework:** FastAPI
- **Database:** MongoDB
- **Templating Engine:** Jinja2
- **Language:** Python 3.11
- **API Documentation:** Swagger UI (OpenAPI)

##  Project Structure
CMS_BACKEND/
        backend/
            _pycache_/
            admin/
            api/
            core/
            models/
            services/
            statics/
            templates/
            _init_.py
            main.py
            
         venv/
         .env
         README.md
         requirements.txt


## Setup Instructions

## 1️. Create and activate virtual environment
bash
python -m venv venv
venv\Scripts\activate   # Windows

 ## 2.Install dependencies 
 pip install -r requirements.txt

 ## 3.Run the application
 uvicorn backend.main:app --reload
Server will run at:
http://127.0.0.1:8000

## Testing the Application

Swagger UI

Open the browser and go to:

http://127.0.0.1:8000/docs
Use this interface to test all API endpoints.



