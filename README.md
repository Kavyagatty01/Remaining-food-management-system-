# 🌿 FoodWise – Food Waste Management System

A web app built with Python, Flask, and SQLite.

## How to Run

### 1. Install Flask
```
pip install flask
```

### 2. Run the app
```
python app.py
```

### 3. Open in your browser
```
http://127.0.0.1:5000
```

## Default Login
- **Username:** admin  
- **Password:** admin123

## Modules
| Module | URL | What it does |
|---|---|---|
| Login | `/` | Admin login |
| Dashboard | `/dashboard` | Stats overview |
| Add Food | `/add` | Add food record |
| View Records | `/records` | See all records |
| Edit/Delete | `/edit/<id>` | Modify records |
| Donate | `/donate` | Record a donation |
| Donations | `/donations` | View donations |

## Project Structure
```
food_waste_app/
├── app.py              ← Main Flask application
├── requirements.txt    ← Python packages needed
├── food_waste.db       ← SQLite database (auto-created)
└── templates/
    ├── base.html       ← Shared layout & nav
    ├── login.html      ← Login page
    ├── dashboard.html  ← Stats dashboard
    ├── add_food.html   ← Add food form
    ├── records.html    ← View all records
    ├── edit_food.html  ← Edit a record
    ├── donate.html     ← Donation form
    └── donations.html  ← View all donations
```
