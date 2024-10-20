import aiohttp
from fastapi import FastAPI, Request, Form, Depends, HTTPException, Response, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Dict, Optional
from starlette.middleware.sessions import SessionMiddleware
import os
from dotenv import load_dotenv

app = FastAPI()
load_dotenv()

API_KEY=os.getenv("API_KEY")
RAPIDAPI_KEY=os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST=os.getenv("RAPIDAPI_HOST")

# Middleware to manage sessions
app.add_middleware(SessionMiddleware, secret_key="abcd")

templates = Jinja2Templates(directory="templates")


users: Dict[str, str] = {}  # Stores username and password pairs


# Authentication function
def get_current_user(session: dict) -> Optional[str]:
    return session.get("username")


# Use aiohttp for async requests to weather API using lat/lon
async def get_weather(lat, lon):
    url = f"https://{RAPIDAPI_HOST}/current?lat={lat}&lon={lon}"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as weather_response:
            if weather_response.status == 200:
                weather_data = await weather_response.json()
                if weather_data['data']:
                    weather = {
                        'description': weather_data['data'][0]['weather']['description'],
                        'icon': weather_data['data'][0]['weather']['icon'],  # For emoji icons
                        'temperature': weather_data['data'][0]['temp'],
                    }
                    return weather
            return None


# Use aiohttp to get latitude and longitude for the location
async def get_coordinates(location):
    geoapify_geocode_url = f"https://api.geoapify.com/v1/geocode/search?text={location}&apiKey={API_KEY}"

    async with aiohttp.ClientSession() as session:
        async with session.get(geoapify_geocode_url) as response:
            if response.status == 200:
                data = await response.json()
                if data['features']:
                    coordinates = data['features'][0]['geometry']['coordinates']
                    return coordinates  # Return longitude and latitude
            return None


# Use aiohttp for async requests to Geoapify API to get tourist spots based on coordinates
async def get_tourist_spots_data(coordinates):
    lon, lat = coordinates
    geoapify_url = f"https://api.geoapify.com/v2/places?categories=tourism&filter=circle:{lon},{lat},5000&limit=20&apiKey={API_KEY}"

    async with aiohttp.ClientSession() as session:
        async with session.get(geoapify_url) as response:
            if response.status == 200:
                places_data = await response.json()
                places = places_data.get("features", [])
                return places
            return None


# Default route to redirect to the login page
@app.get('/', response_class=RedirectResponse)
async def homepage():
    return RedirectResponse(url="/login")


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.post("/register", response_class=HTMLResponse)
async def register(request: Request, username: str = Form(...), password: str = Form(...)):
    if username in users:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Username already exists."
        })
    
    # Store user credentials
    users[username] = password
    
    return templates.TemplateResponse("login.html", {
        "request": request,
        "message": "Registration successful. Please log in."
    })


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login", response_class=RedirectResponse)
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username in users and users[username] == password:
        request.session["username"] = username  # Store username in session
        return RedirectResponse(url="/form")  # Redirect to the form page after successful login
    else:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid credentials."
        })

@app.get("/form", response_class=HTMLResponse)
async def form_page(request: Request):
    return templates.TemplateResponse("form.html", {"request": request})

@app.post("/form", response_class=HTMLResponse)
async def form_page(request: Request):
    username = get_current_user(request.session)
    if not username:
        return RedirectResponse(url="/login")  # Redirect to login if not authenticated
    return templates.TemplateResponse("form.html", {"request": request, "username": username})


@app.get("/logout", response_class=HTMLResponse)
async def logout(request: Request):
    response = RedirectResponse(url="/login")
    request.session.clear()  # Clear the session on logout
    return response


@app.post("/results", response_class=HTMLResponse)
async def get_tourist_spots(request: Request, location: str = Form(...)):
    coordinates = await get_coordinates(location)

    if not coordinates:
        return templates.TemplateResponse("results.html", {
            "request": request, "location": location, "error": "Location not found."
        })

    places = await get_tourist_spots_data(coordinates)

    if not places:
        return templates.TemplateResponse("results.html", {
            "request": request, "location": location, "error": "No tourist spots found."
        })

    lon, lat = coordinates
    weather = await get_weather(lat, lon)

    if weather is None:
        return templates.TemplateResponse("results.html", {
            "request": request, "location": location, "places": places, "error": "Failed to fetch weather."
        })

    # Iterate over places and check for address in properties
    for place in places:
        # Assuming place is a dict and 'properties' is a key in the dict
        address = place.get('properties', {}).get('address', 'Address not available')
        place['properties']['address'] = address  # Add address to the dictionary

    return templates.TemplateResponse("results.html", {
        "request": request,
        "location": location,
        "places": places,
        "weather": weather
    })
