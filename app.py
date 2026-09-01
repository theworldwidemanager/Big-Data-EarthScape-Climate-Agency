
import os
from dotenv import load_dotenv
load_dotenv()

# Import necessary Flask modules and MongoDB extensions
from flask import Flask, json, request,Blueprint, render_template, redirect, url_for, jsonify, flash, session
from flask_pymongo import PyMongo
import pandas as pd 
import csv , io
import google.generativeai as genai
from pymongo import MongoClient
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash # For secure password handling
from bson.objectid import ObjectId # To work with MongoDB's default _id field (optional but good practice)
import datetime
from flask_mail import Mail, Message # For sending emails (optional, if you want to implement email notifications)
import re


# Initialize the Flask application
app = Flask(__name__)

visualize_bp = Blueprint('visualize', __name__)

# ✅ Mail setup (put in main file once globally)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME')
mail = Mail(app)

# --- Flask Configuration for MongoDB ---
# We have switched to a local URI to avoid DNS resolution errors (NXDOMAIN) with MongoDB Atlas.
app.config["MONGO_URI"] = os.environ.get('MONGO_URI')
app.secret_key = os.environ.get('FLASK_SECRET_KEY')

# Initialize PyMongo safely
try:
    mongo = PyMongo(app)
    # We define collections here
    users_collection = mongo.db.users
    feedback_collection = mongo.db.feedback
    climate_collection = mongo.db.climate_records
except Exception as e:
    print(f"⚠️ MongoDB Connection Trace: {e}")
    # Fallback to avoid crashes on startup
    mongo = None
    users_collection = None
    feedback_collection = None
    climate_collection = None

genai.configure(api_key=os.environ.get('GEMINI_API_KEY'))

import requests

OPENWEATHER_API_KEY = os.environ.get('OPENWEATHER_API_KEY')

@app.route("/chatbot", methods=["POST"])
def chatbot():
    user_msg = request.form.get("message", "").strip()

    try:
        model = genai.GenerativeModel("gemini-2.0-flash")

        # Step 1: Check if message is weather-related
        weather_check_prompt = f"""
The user will input a message. You have to say only "Yes" or "No" based on whether the message is related to weather, climate, temperature, humidity, rain, or environmental conditions.

Message: "{user_msg}"
Reply with only Yes or No.
"""
        weather_check = model.generate_content(weather_check_prompt)
        is_weather_related = weather_check.text.strip().lower() == "yes"

        # Step 2: If weather-related, extract city
        if is_weather_related:
            location_prompt = f"""
Extract the city or location name from this message. If none found, say "None".

Message: "{user_msg}"
City:
"""
            city_response = model.generate_content(location_prompt)
            city_raw = city_response.text.strip()
            city_cleaned = re.sub(r"[^a-zA-Z\s]", "", city_raw).strip().title()

            if city_cleaned and city_cleaned.lower() != "none":
                # Step 3: Detect weather intent (forecast or current)
                intent_prompt = f"""
Decide whether the message is asking about "current" weather or "forecast" (future weather like tomorrow).

Message: "{user_msg}"
Reply with only one word: current or forecast.
"""
                intent_response = model.generate_content(intent_prompt)
                weather_intent = intent_response.text.strip().lower()

                try:
                    if weather_intent == "forecast":
                        url = f"http://api.openweathermap.org/data/2.5/forecast?q={city_cleaned}&appid={OPENWEATHER_API_KEY}&units=metric"
                        res = requests.get(url, timeout=5)
                        res.raise_for_status()
                        forecast_data = res.json()

                        if forecast_data.get("cod") == "200":
                            # We'll pick the first forecast entry (next few hours, usually ~3 hrs ahead)
                            next_data = forecast_data["list"][0]
                            temp = next_data["main"]["temp"]
                            desc = next_data["weather"][0]["description"].capitalize()

                            reply = f"🌦️ {city_cleaned} ka forecast: Aane wale waqt mein temperature {temp}°C hoga, weather: {desc}."
                            return jsonify({ "reply": reply })
                        else:
                            return jsonify({ "reply": f"⚠️ {city_cleaned} ka forecast data mil nahi saka." })

                    else:  # default to current
                        url = f"http://api.openweathermap.org/data/2.5/weather?q={city_cleaned}&appid={OPENWEATHER_API_KEY}&units=metric"
                        res = requests.get(url, timeout=5)
                        res.raise_for_status()
                        weather_data = res.json()

                        if weather_data.get("cod") == 200:
                            temp = weather_data["main"]["temp"]
                            desc = weather_data["weather"][0]["description"].capitalize()
                            humidity = weather_data["main"]["humidity"]

                            reply = f"📍 {city_cleaned} mein temperature abhi {temp}°C hai, weather is: {desc}, aur humidity {humidity}% hai."
                            return jsonify({ "reply": reply })
                        else:
                            return jsonify({ "reply": f"⚠️ Sorry, {city_cleaned} ka weather data mil nahi saka." })

                except requests.exceptions.RequestException as e:
                    print("❌ Weather API error:", e)
                    return jsonify({ "reply": "⚠️ Weather service is not responding at the moment. Try again later." })

            else:
                return jsonify({ "reply": "⚠️ Please mention the city name so I can fetch the weather data." })

        # Step 4: Check if dashboard-related
        dashboard_check_prompt = f"""
The user will input a message. You have to say only "Yes" or "No" based on whether the message is related to:
- weather/climate/temperature/humidity
- data upload, CSV files
- visualizations, graphs
- alerts or notifications
- profile or account changes
- machine learning models (e.g. regression/classification)
- dashboard-related help

Message: "{user_msg}"
Reply with only Yes or No.
"""
        dashboard_check = model.generate_content(dashboard_check_prompt)
        is_dashboard_related = dashboard_check.text.strip().lower() == "yes"

        if is_dashboard_related:
            dashboard_prompt = f"""
You are a smart and helpful chatbot for the EarthScape Climate Dashboard.

The user will ask questions related to:

🌦️ Climate Predictions:
- Rainfall, humidity, or temperature prediction
- Will it rain tomorrow?
- What is the current humidity?

📁 Data Upload:
- Did my CSV upload?
- Give summary of uploaded data
- Are there missing values?
- Train model on my uploaded file

📊 Dashboard Help:
- What does this dashboard show?
- How to use the Visualize tab?
- What are alerts?

🧠 Machine Learning:
- Should I use classification or regression?
- Which model should I choose? (Linear Regression, Decision Tree, etc.)
- How accurate is my model?
- Retrain the model

🔔 Alerts:
- What do alerts mean?
- Show recent climate alerts
- How to review alerts?

🧑‍💻 User Profile:
- How to update my profile?
- Can I change my role?
- How do I upload my profile picture?

🔐 Account:
- How to logout?
- How to reset my password?

⚠️ Only respond to relevant questions. Keep replies **short**, **clear**, and **easy to understand**. Prefer **Roman Urdu** or **simple English** not Hindi.

User: {user_msg}
Bot:
"""
            dashboard_response = model.generate_content(dashboard_prompt)
            return jsonify({ "reply": dashboard_response.text.strip() })

        # Step 5: Not related
        return jsonify({
            "reply": "⚠️ Sorry, I can only help with climate or dashboard-related queries. Please ask something about weather, data upload, visualizations, alerts, or your profile."
        })

    except Exception as e:
        print("Error:", e)
        return jsonify({ "reply": "⚠️ Something went wrong. Please try again later." }), 500
    

    
# --- Registration Route ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        role = "analyst"  # ✅ Force default role to Analyst

        if not all([full_name, email, password]):
            flash('All fields are required!', 'danger')
            return render_template('register.html')

        existing_user = users_collection.find_one({'email': email})
        if existing_user:
            flash('This email address is already registered. Please try logging in or use a different email.', 'danger')
            return render_template('register.html')

        hashed_password = generate_password_hash(password)
        user_data = {
            'full_name': full_name,
            'email': email,
            'password_hash': hashed_password,
            'role': role  # Always Analyst
        }

        try:
            users_collection.insert_one(user_data)
            flash('Account created successfully! You can now log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f'An error occurred during registration: {e}', 'danger')
            return render_template('register.html')

    return render_template('register.html')


@app.route('/', methods=['GET'])  # Default route redirects to login
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user_data = users_collection.find_one({'email': email})

        if user_data and check_password_hash(user_data['password_hash'], password):
            session['user_id'] = str(user_data['_id'])
            session['username'] = user_data['full_name']
            session['user_role'] = user_data['role']

            # Redirect based on role
            if user_data['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user_data['role'] == 'analyst':
                return redirect(url_for('analyst_dashboard'))
            else:
                flash("Access denied: Unknown role", "danger")
                return redirect(url_for('login'))
        else:
            flash("Invalid email or password", "danger")
            return render_template('login.html')

    return render_template('login.html')


#---------------------------------------------------------------------------------------------------------------
#------------------------------------------Admin Dashboard Route (Main)--------------------------------------
#---------------------------------------------------------------------------------------------------------------

@app.route('/admin')
def admin_dashboard():
    user_id = session.get('user_id')
    user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
    return render_template('layout/admin_dashboard.html', user=user)

@app.route('/admin/home')
def admin_home():
    return render_template('admin/admin_home.html')



@app.route('/admin/users')
def admin_users():
    users = list(mongo.db.users.find().sort('full_name', 1))
    return render_template('admin/admin_users.html', users=users)

@app.route('/admin/users/delete/<id>', methods=['POST'])
def delete_user(id):
    mongo.db.users.delete_one({'_id': ObjectId(id)})
    return '', 204

@app.route('/admin/users/edit/<id>', methods=['POST'])
def edit_user(id):
    data = request.get_json()
    mongo.db.users.update_one(
        {'_id': ObjectId(id)},
        {'$set': {
            'full_name': data['full_name'],
            'email': data['email'],
            'role': data['role']
        }}
    )
    return '', 204


# ✅ Improved CSV Upload Route with Validation, Alerts, and Prediction Options
@app.route("/admin/upload", methods=["GET", "POST"])
def upload_climate_records():
    if request.method == 'POST':
        if "file" not in request.files:
            return jsonify({"success": False, "message": "No file uploaded."})

        file = request.files["file"]
        filename = file.filename.lower()

        if filename.endswith('.csv'):
            try:
                stream = io.StringIO(file.stream.read().decode("UTF8"))
                reader = csv.DictReader(stream)
                data = list(reader)

                required_fields = ['temperature', 'humidity', 'rainfall', 'wind_speed']
                inserted = 0
                skipped = 0
                errors = []
                alerts = []

                for i, row in enumerate(data):
                    if not all(field in row and row[field].strip() for field in required_fields):
                        errors.append(f"Row {i+2}: Missing fields.")
                        skipped += 1
                        continue

                    try:
                        temp = float(row["temperature"])
                        hum = float(row["humidity"])
                        rain = float(row["rainfall"])
                        wind = float(row["wind_speed"])

                        record = {
                            "temperature": temp,
                            "humidity": hum,
                            "rainfall": rain,
                            "wind_speed": wind,
                            "timestamp": datetime.datetime.utcnow()
                        }

                        # Skip duplicates
                        if mongo.db.climate_records.find_one({
                            "temperature": temp,
                            "humidity": hum,
                            "rainfall": rain,
                            "wind_speed": wind
                        }):
                            skipped += 1
                            continue

                        mongo.db.climate_records.insert_one(record)
                        inserted += 1

                        # ✅ Create individual alerts for each condition
                        if temp > 40:
                            alerts.append({
                                "type": "High Temperature",
                                "value": temp,
                                "timestamp": datetime.datetime.utcnow(),
                                "source": "CSV Upload",
                                "admin_email": session.get('username', 'unknown')
                            })
                        if hum < 20:
                            alerts.append({
                                "type": "Low Humidity",
                                "value": hum,
                                "timestamp": datetime.datetime.utcnow(),
                                "source": "CSV Upload",
                                "admin_email": session.get('username', 'unknown')
                            })
                        if rain > 20:
                            alerts.append({
                                "type": "Heavy Rainfall",
                                "value": rain,
                                "timestamp": datetime.datetime.utcnow(),
                                "source": "CSV Upload",
                                "admin_email": session.get('username', 'unknown')
                            })

                    except Exception:
                        errors.append(f"Row {i+2}: Invalid numeric values.")
                        skipped += 1

                # ✅ Store all alerts
                if alerts:
                    mongo.db.alerts.insert_many(alerts)

                return jsonify({
                    "success": True,
                    "inserted": inserted,
                    "skipped": skipped,
                    "errors": errors,
                    "alerts": alerts,
                    "show_prediction": True
                })

            except Exception as e:
                return jsonify({"success": False, "message": f"Error processing file: {e}"})

        elif filename.endswith('.json'):
            try:
                json_data = file.read()
                records = json.loads(json_data)
                inserted = 0
                for record in records:
                    mongo.db.climate_records.insert_one(record)
                    inserted += 1
                return jsonify({"success": True, "inserted": inserted, "message": "JSON file uploaded."})
            except Exception as e:
                return jsonify({"success": False, "message": str(e)})
        else:
            return jsonify({"success": False, "message": "Only CSV or JSON files allowed."})

    return render_template("admin/admin_uploads.html")


    if request.method == 'POST':
        if "file" not in request.files:
            return jsonify({"success": False, "message": "No file uploaded."})

        file = request.files["file"]
        filename = file.filename.lower()

        if filename.endswith('.csv'):
            try:
                stream = io.StringIO(file.stream.read().decode("UTF8"))
                reader = csv.DictReader(stream)
                data = list(reader)

                required_fields = ['temperature', 'humidity', 'rainfall', 'wind_speed']
                inserted = 0
                skipped = 0
                errors = []
                alerts = []

                for i, row in enumerate(data):
                    # Check required fields
                    if not all(field in row and row[field].strip() for field in required_fields):
                        errors.append(f"Row {i+2}: Missing fields.")
                        skipped += 1
                        continue

                    try:
                        temp = float(row["temperature"])
                        hum = float(row["humidity"])
                        rain = float(row["rainfall"])
                        wind = float(row["wind_speed"])

                        record = {
                            "temperature": temp,
                            "humidity": hum,
                            "rainfall": rain,
                            "wind_speed": wind,
                            "timestamp": datetime.datetime.utcnow()
                        }

                        # Skip duplicates
                        if mongo.db.climate_records.find_one({
                            "temperature": temp,
                            "humidity": hum,
                            "rainfall": rain,
                            "wind_speed": wind
                        }):
                            skipped += 1
                            continue

                        mongo.db.climate_records.insert_one(record)
                        inserted += 1

                        # Trigger alert if threshold exceeds
                        if temp > 40 or hum < 20 or rain > 20:
                            alerts.append({
                                "type": "High Temp/Humidity/Rainfall",
                                "details": record,
                                "timestamp": datetime.datetime.utcnow(),
                                "admin_email": session.get('username', 'unknown')
                            })

                    except Exception:
                        errors.append(f"Row {i+2}: Invalid numeric values.")
                        skipped += 1

                # Store alerts
                if alerts:
                    mongo.db.alerts.insert_many(alerts)

                return jsonify({
                    "success": True,
                    "inserted": inserted,
                    "skipped": skipped,
                    "errors": errors,
                    "alerts": alerts,
                    "show_prediction": True  # ✅ frontend should show prediction UI
                })

            except Exception as e:
                return jsonify({"success": False, "message": f"Error processing file: {e}"})

        elif filename.endswith('.json'):
            try:
                json_data = file.read()
                records = json.loads(json_data)
                inserted = 0
                for record in records:
                    mongo.db.climate_records.insert_one(record)
                    inserted += 1
                return jsonify({"success": True, "inserted": inserted, "message": "JSON file uploaded."})
            except Exception as e:
                return jsonify({"success": False, "message": str(e)})
        else:
            return jsonify({"success": False, "message": "Only CSV or JSON files allowed."})

    return render_template("admin/admin_uploads.html")
@app.route('/admin/alerts')
def admin_alerts():
    return render_template('admin/admin_alerts.html')

@app.route('/admin/model')
def admin_model():
    return render_template('admin/admin_model.html')
@app.route('/api/model-predictions')
def model_predictions():
    # Example dummy prediction data
    predictions = {
        "labels": ["2025-06-01", "2025-06-02", "2025-06-03"],
        "humidity": [55, 61, 58]
    }
    return jsonify(predictions)

from sklearn.tree import DecisionTreeRegressor
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.svm import SVR
from sklearn.preprocessing import PolynomialFeatures
from sklearn.pipeline import make_pipeline

@app.route('/admin/train-model', methods=['POST'])
def train_model_admin():
    try:
        target = request.form.get("target")
        model_type = request.form.get("ml_model")
        df = pd.DataFrame(list(mongo.db.climate_records.find()))
        df = df[['temperature', 'humidity', 'rainfall', 'wind_speed']].dropna()

        # ✅ Select features based on target
        if target == "humidity":
            features = ["temperature"]
        elif target == "rainfall":
            features = ["temperature", "humidity"]
        elif target == "temperature":
            features = ["humidity", "rainfall"]
        else:
            return jsonify({"success": False, "error": "Invalid target"})

        df = df.dropna(subset=features + [target])

        # ✅ Model selection
        if model_type == "decision_tree":
            model = DecisionTreeRegressor()
        elif model_type == "linear_regression":
            model = LinearRegression()
        elif model_type == "svr":
            model = SVR(kernel='rbf')
        elif model_type == "polynomial":
            model = make_pipeline(PolynomialFeatures(degree=2), LinearRegression())
        elif model_type == "Random":
            model = RandomForestRegressor()
        else:
            return jsonify({"success": False, "error": "Invalid model type"})

        model.fit(df[features], df[target])

        # ✅ Input values
        temp = float(request.form.get('temp_input', 0))
        humidity = request.form.get('humidity_input')
        rainfall = request.form.get('rainfall_input')
        wind_speed = request.form.get('wind_speed_input')

        input_features = {
            "temperature": temp,
            "humidity": float(humidity) if humidity else 0,
            "rainfall": float(rainfall) if rainfall else 0
        }

        input_vector = [input_features[f] for f in features]
        prediction = round(model.predict([input_vector])[0], 2)

        record = {
            "timestamp": datetime.datetime.utcnow(),
            "temperature": temp,
            "humidity": float(humidity) if humidity else (prediction if target == 'humidity' else None),
            "rainfall": float(rainfall) if rainfall else (prediction if target == 'rainfall' else None),
            "wind_speed": float(wind_speed) if wind_speed else None,
            "model_used": model_type,
            "source": "Model + Manual"
        }

        if target == "temperature":
            record['temperature'] = prediction

        mongo.db.climate_records.insert_one(record)

        # ✅ ALERT GENERATION
        alert_messages = []
        if record.get("temperature") and record["temperature"] > 40:
            alert_messages.append(f"🔥 High temperature: {record['temperature']}°C")
        if record.get("humidity") and record["humidity"] < 20:
            alert_messages.append(f"💧 Low humidity: {record['humidity']}%")
        if record.get("rainfall") and record["rainfall"] > 20:
            alert_messages.append(f"☔️ Heavy rainfall: {record['rainfall']} mm")

        if alert_messages:
            mongo.db.climate_alerts.insert_one({
                "timestamp": datetime.datetime.utcnow(),
                "alerts": alert_messages,
                "source": "model",
                "username": session.get('username', 'unknown')
            })

            # ✅ Send alert email
            user = mongo.db.users.find_one({'username': session.get('username')})
            if user and 'email' in user:
                try:
                    subject_line = "📢 EarthScape Climate Agency - Climate Alert Notification"
                    message_body = f"""
Dear {user['username']},

We hope you're doing well.

This is an automated alert from EarthScape Climate Agency regarding unusual climate conditions observed during your recent prediction request:

{chr(10).join(f"- {msg}" for msg in alert_messages)}

Please take necessary precautions if you're in the affected area.

Stay safe and thank you for using EarthScape Climate Agency.

Best regards,  
🌿 EarthScape Climate Team
"""

                    msg = Message(
                        subject=subject_line,
                        sender=app.config['MAIL_USERNAME'],
                        recipients=[user['email']],
                        body=message_body
                    )
                    mail.send(msg)

                    # ✅ Log email activity
                    mongo.db.activities.insert_one({
                        "username": user['username'],
                        "action": f"Alert email sent to {user['email']}",
                        "timestamp": datetime.datetime.utcnow()
                    })

                except Exception as e:
                    print(f"❌ Email failed: {e}")

        # ✅ Format prediction display
        if target == "temperature":
            display_value = f"{prediction}°C"
        elif target == "humidity":
            display_value = f"{prediction}%"
        elif target == "rainfall":
            display_value = f"{prediction} mm"
        else:
            display_value = str(prediction)

        # ✅ Log model training
        mongo.db.activities.insert_one({
            "username": session.get('username', 'unknown'),
            "action": f"Trained {model_type.replace('_', ' ').title()} model on {target.capitalize()}",
            "timestamp": datetime.datetime.utcnow()
        })

        # ✅ Save prediction
        mongo.db.prediction_history.insert_one({
            "username": session.get("username", "unknown"),
            "timestamp": datetime.datetime.utcnow(),
            "target": target,
            "predicted_value": prediction,
            "model_used": model_type,
            "temperature": temp if temp else None,
            "humidity": float(humidity) if humidity else None,
            "rainfall": float(rainfall) if rainfall else None,
            "wind_speed": float(wind_speed) if wind_speed else None
        })

        return jsonify({
            "success": True,
            "target": target.capitalize(),
            "value": display_value,
            "alerts": alert_messages
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})




# Assuming you have 'db' instead of 'mongo.db' if you did `db = mongo_client.get_database()`
# If using 'mongo', then it's 'mongo.db.notifications'
@app.route('/api/climate-overview')
def climate_overview():
    try:
        records = list(mongo.db.climate_records.find({}, {
            '_id': 0,
            'timestamp': 1,
            'temperature': 1,
            'rainfall': 1,
            'humidity': 1,
            'wind_speed': 1
        }))

        chart_data = {
            "labels": [],
            "temperature": [],
            "rainfall": [],
            "humidity": [],
            "wind_speed": []
        }

        for r in records:
            try:
                # Get timestamp
                ts = r.get("timestamp")
                if isinstance(ts, str):
                    label = ts[:10]
                elif hasattr(ts, 'isoformat'):
                    label = ts.isoformat()[:10]
                else:
                    label = "Unknown"

                chart_data["labels"].append(label)

                # Use 0.0 as fallback if value is None or not float-compatible
                chart_data["temperature"].append(float(r.get("temperature") or 0.0))
                chart_data["rainfall"].append(float(r.get("rainfall") or 0.0))
                chart_data["humidity"].append(float(r.get("humidity") or 0.0))
                chart_data["wind_speed"].append(float(r.get("wind_speed") or 0.0))

            except Exception as record_error:
                # Skip the broken record silently
                continue

        return jsonify(chart_data)

    except Exception as e:
        print("Fatal error in /api/climate-overview:", e)
        return jsonify({"error": str(e)}), 500
    
@app.route('/admin/feedback')
def admin_feedback():
    feedbacks = list(mongo.db.feedback.find().sort('timestamp', -1))
    return render_template('admin/admin_feedback.html', feedbacks=feedbacks)


from bson import ObjectId
from flask import request, jsonify

# --- DELETE FEEDBACK ---
@app.route('/admin/feedback/delete/<id>', methods=['POST'])
def delete_feedback(id):
    print("Deleting feedback ID:", id)  # ✅ Removed emoji to avoid Unicode error
    try:
        mongo.db.feedback.delete_one({'_id': ObjectId(id)})
        return '', 204
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- EDIT FEEDBACK ---
@app.route('/admin/feedback/edit/<id>', methods=['POST'])
def edit_feedback(id):
    try:
        data = request.get_json()
        mongo.db.feedback.update_one(
            {'_id': ObjectId(id)},
            {'$set': {'message': data['message']}}
        )
        return '', 204
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Fetch profile for form
@app.route('/admin/profile', methods=['GET'])
def admin_profile():
    user_id = session.get('user_id')  # assume you're storing user id in session
    user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
    return render_template('admin/admin_profile.html', user=user)

import os
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'static/uploads/profile_pics'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/admin/profile/update', methods=['POST'])
def update_admin_profile():
    user_id = session.get('user_id')
    updated_data = {
        'username': request.form['username'],
        'email': request.form['email'],
        'bio': request.form['bio'],
    }

    # Handle image upload
    profile_img = request.files.get('profile_img')
    if profile_img and profile_img.filename != '':
        filename = secure_filename(profile_img.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        profile_img.save(filepath)
        updated_data['profile_img'] = f'/static/uploads/profile_pics/{filename}'

    mongo.db.users.update_one({'_id': ObjectId(user_id)}, {'$set': updated_data})
    return jsonify({'status': 'success'})

@app.route('/logout')
def logout():
    session.clear()  # ✅ Clear all session data
    return redirect(url_for('login'))  # ✅ Redirect to login page



#---------------------------------------------------------------------------------------------------------------
#------------------------------------------Analyst Dashboard Route (Main)--------------------------------------
#-------------------------------------------------------------------------------------------------------------

from bson import ObjectId
from flask import session, render_template

@app.route('/analyst')
def analyst_dashboard():
    user_id = session.get('user_id')
    user = mongo.db.users.find_one({'_id': ObjectId(user_id)})

    total_records = mongo.db.climate_records.count_documents({})
    total_alerts = mongo.db.climate_alerts.count_documents({})
    predictions_count = mongo.db.climate_records.count_documents({'source': 'Model + Manual'})

    # ✅ Fetch recent activity
    username = session.get('username', 'unknown')
    recent_activities = list(mongo.db.activities.find(
        {"username": username}
    ).sort("timestamp", -1).limit(5))

    return render_template('layout/analyst_dashboard.html', user=user,
                           stats={
                               "records": total_records,
                               "alerts": total_alerts,
                               "predictions": predictions_count,
                               "visualizations": 0
                           },
                           recent_activities=recent_activities)


@app.route("/analyst/home")
def analyst_dashboard_home():
    user_id = session.get('user_id')
    user = mongo.db.users.find_one({'_id': ObjectId(user_id)})

    total_records = mongo.db.climate_records.count_documents({})
    total_alerts = mongo.db.climate_alerts.count_documents({})
    predictions_count = mongo.db.climate_records.count_documents({'source': 'Model + Manual'})

    # ✅ Fetch recent activities
    username = session.get('username', 'unknown')
    recent_activities = list(mongo.db.activities.find(
        {"username": username}
    ).sort("timestamp", -1).limit(5))

    return render_template('analyst/analyst_home.html', user=user,
                           stats={
                               "records": total_records,
                               "alerts": total_alerts,
                               "predictions": predictions_count,
                               "visualizations": 0
                           },
                           recent_activities=recent_activities)

# Fetch profile for form
@app.route('/analyst/profile', methods=['GET'])
def analyst_profile():
    user_id = session.get('user_id')  # assume you're storing user id in session
    user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
    return render_template('analyst/analyst_profile.html', user=user)

import os
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'static/uploads/profile_pics'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/analyst/profile/update', methods=['POST'])
def update_analyst_profile():
    user_id = session.get('user_id')
    updated_data = {
        'username': request.form['username'],
        'email': request.form['email'],
        'bio': request.form['bio'],
    }

    # Handle image upload
    profile_img = request.files.get('profile_img')
    if profile_img and profile_img.filename != '':
        filename = secure_filename(profile_img.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        profile_img.save(filepath)
        updated_data['profile_img'] = f'/static/uploads/profile_pics/{filename}'

    mongo.db.users.update_one({'_id': ObjectId(user_id)}, {'$set': updated_data})
    return jsonify({'status': 'success'})

# ✅ Improved CSV Upload Route with Validation, Alerts, and Prediction Options
@app.route("/analyst/upload", methods=["GET", "POST"])
def upload_climate_records_analyst():
    if request.method == 'POST':
        if "file" not in request.files:
            return jsonify({"success": False, "message": "No file uploaded."})

        file = request.files["file"]
        filename = file.filename.lower()

        if filename.endswith('.csv'):
            try:
                stream = io.StringIO(file.stream.read().decode("UTF8"))
                reader = csv.DictReader(stream)
                data = list(reader)

                required_fields = ['temperature', 'humidity', 'rainfall', 'wind_speed']
                inserted = 0
                skipped = 0
                errors = []
                alerts = []

                for i, row in enumerate(data):
                    if not all(field in row and row[field].strip() for field in required_fields):
                        errors.append(f"Row {i+2}: Missing fields.")
                        skipped += 1
                        continue

                    try:
                        temp = float(row["temperature"])
                        hum = float(row["humidity"])
                        rain = float(row["rainfall"])
                        wind = float(row["wind_speed"])

                        record = {
                            "temperature": temp,
                            "humidity": hum,
                            "rainfall": rain,
                            "wind_speed": wind,
                            "timestamp": datetime.datetime.utcnow()
                        }

                        # Skip duplicates
                        if mongo.db.climate_records.find_one({
                            "temperature": temp,
                            "humidity": hum,
                            "rainfall": rain,
                            "wind_speed": wind
                        }):
                            skipped += 1
                            continue

                        mongo.db.climate_records.insert_one(record)
                        inserted += 1

                        # ✅ Create individual alerts for each condition
                        if temp > 40:
                            alerts.append({
                                "type": "High Temperature",
                                "value": temp,
                                "timestamp": datetime.datetime.utcnow(),
                                "source": "CSV Upload",
                                "admin_email": session.get('username', 'unknown')
                            })
                        if hum < 20:
                            alerts.append({
                                "type": "Low Humidity",
                                "value": hum,
                                "timestamp": datetime.datetime.utcnow(),
                                "source": "CSV Upload",
                                "admin_email": session.get('username', 'unknown')
                            })
                        if rain > 20:
                            alerts.append({
                                "type": "Heavy Rainfall",
                                "value": rain,
                                "timestamp": datetime.datetime.utcnow(),
                                "source": "CSV Upload",
                                "admin_email": session.get('username', 'unknown')
                            })

                    except Exception:
                        errors.append(f"Row {i+2}: Invalid numeric values.")
                        skipped += 1

                # ✅ Store all alerts
                if alerts:
                    mongo.db.alerts.insert_many(alerts)

                # ✅ Log CSV upload
                mongo.db.activities.insert_one({
                    "username": session.get('username', 'unknown'),
                    "action": f"Uploaded CSV: {inserted} records inserted, {skipped} skipped",
                    "timestamp": datetime.datetime.utcnow()
                })

                return jsonify({
                    "success": True,
                    "inserted": inserted,
                    "skipped": skipped,
                    "errors": errors,
                    "alerts": alerts,
                    "show_prediction": True
                })

            except Exception as e:
                return jsonify({"success": False, "message": f"Error processing file: {e}"})

        elif filename.endswith('.json'):
            try:
                json_data = file.read()
                records = json.loads(json_data)
                inserted = 0
                for record in records:
                    mongo.db.climate_records.insert_one(record)
                    inserted += 1
                return jsonify({"success": True, "inserted": inserted, "message": "JSON file uploaded."})
            except Exception as e:
                return jsonify({"success": False, "message": str(e)})
        else:
            return jsonify({"success": False, "message": "Only CSV or JSON files allowed."})

    return render_template("analyst/analyst_upload.html")


@app.route('/analyst/train-model', methods=['POST'])
def train_model_analyst():
    try:
        target = request.form.get("target")
        model_type = request.form.get("ml_model")
        df = pd.DataFrame(list(mongo.db.climate_records.find()))
        df = df[['temperature', 'humidity', 'rainfall', 'wind_speed']].dropna()

        # ✅ Select features based on target
        if target == "humidity":
            features = ["temperature"]
        elif target == "rainfall":
            features = ["temperature", "humidity"]
        elif target == "temperature":
            features = ["humidity", "rainfall"]
        else:
            return jsonify({"success": False, "error": "Invalid target"})

        df = df.dropna(subset=features + [target])

        # ✅ Model selection
        if model_type == "decision_tree":
            model = DecisionTreeRegressor()
        elif model_type == "linear_regression":
            model = LinearRegression()
        elif model_type == "svr":
            model = SVR(kernel='rbf')
        elif model_type == "polynomial":
            model = make_pipeline(PolynomialFeatures(degree=2), LinearRegression())
        elif model_type == "Random":
            model = RandomForestRegressor()
        else:
            return jsonify({"success": False, "error": "Invalid model type"})

        model.fit(df[features], df[target])

        # ✅ Input values
        temp = float(request.form.get('temp_input', 0))
        humidity = request.form.get('humidity_input')
        rainfall = request.form.get('rainfall_input')
        wind_speed = request.form.get('wind_speed_input')

        input_features = {
            "temperature": temp,
            "humidity": float(humidity) if humidity else 0,
            "rainfall": float(rainfall) if rainfall else 0
        }

        input_vector = [input_features[f] for f in features]
        prediction = round(model.predict([input_vector])[0], 2)

        record = {
            "timestamp": datetime.datetime.utcnow(),
            "temperature": temp,
            "humidity": float(humidity) if humidity else (prediction if target == 'humidity' else None),
            "rainfall": float(rainfall) if rainfall else (prediction if target == 'rainfall' else None),
            "wind_speed": float(wind_speed) if wind_speed else None,
            "model_used": model_type,
            "source": "Model + Manual"
        }

        if target == "temperature":
            record['temperature'] = prediction

        mongo.db.climate_records.insert_one(record)

        # ✅ ALERT GENERATION
        alert_messages = []
        if record.get("temperature") and record["temperature"] > 40:
            alert_messages.append(f"🔥 High temperature: {record['temperature']}°C")
        if record.get("humidity") and record["humidity"] < 20:
            alert_messages.append(f"💧 Low humidity: {record['humidity']}%")
        if record.get("rainfall") and record["rainfall"] > 20:
            alert_messages.append(f"☔️ Heavy rainfall: {record['rainfall']} mm")

        if alert_messages:
            mongo.db.climate_alerts.insert_one({
                "timestamp": datetime.datetime.utcnow(),
                "alerts": alert_messages,
                "source": "model",
                "username": session.get('username', 'unknown')
            })

            # ✅ Send alert email
            user = mongo.db.users.find_one({'username': session.get('username')})
            if user and 'email' in user:
                try:
                    subject_line = "📢 EarthScape Climate Agency - Climate Alert Notification"
                    message_body = f"""
Dear {user['username']},

We hope you're doing well.

This is an automated alert from EarthScape Climate Agency regarding unusual climate conditions observed during your recent prediction request:

{chr(10).join(f"- {msg}" for msg in alert_messages)}

Please take necessary precautions if you're in the affected area.

Stay safe and thank you for using EarthScape Climate Agency.

Best regards,  
🌿 EarthScape Climate Team
"""

                    msg = Message(
                        subject=subject_line,
                        sender=app.config['MAIL_USERNAME'],
                        recipients=[user['email']],
                        body=message_body
                    )
                    mail.send(msg)

                    # ✅ Log email activity
                    mongo.db.activities.insert_one({
                        "username": user['username'],
                        "action": f"Alert email sent to {user['email']}",
                        "timestamp": datetime.datetime.utcnow()
                    })

                except Exception as e:
                    print(f"❌ Email failed: {e}")

        # ✅ Format prediction display
        if target == "temperature":
            display_value = f"{prediction}°C"
        elif target == "humidity":
            display_value = f"{prediction}%"
        elif target == "rainfall":
            display_value = f"{prediction} mm"
        else:
            display_value = str(prediction)

        # ✅ Log model training
        mongo.db.activities.insert_one({
            "username": session.get('username', 'unknown'),
            "action": f"Trained {model_type.replace('_', ' ').title()} model on {target.capitalize()}",
            "timestamp": datetime.datetime.utcnow()
        })

        # ✅ Save prediction
        mongo.db.prediction_history.insert_one({
            "username": session.get("username", "unknown"),
            "timestamp": datetime.datetime.utcnow(),
            "target": target,
            "predicted_value": prediction,
            "model_used": model_type,
            "temperature": temp if temp else None,
            "humidity": float(humidity) if humidity else None,
            "rainfall": float(rainfall) if rainfall else None,
            "wind_speed": float(wind_speed) if wind_speed else None
        })

        return jsonify({
            "success": True,
            "target": target.capitalize(),
            "value": display_value,
            "alerts": alert_messages
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})



@app.route('/analyst/visualize')
def analyst_visualize():
    return render_template('analyst/analyst_visualize.html')
@app.route('/analyst/model')
def analyst_model():
    return render_template('analyst/analyst_model.html')

@app.route('/api/climate-data')
def get_climate_records():
    

    data = list(mongo.db.climate_records.find({}, {'_id': 0, 'timestamp': 1, 'temperature': 1, 'rainfall': 1}))

    formatted = []
    for d in data:
        ts = d.get('timestamp')

        date_str = "unknown"
        try:
            if isinstance(ts, datetime):
                date_str = ts.strftime('%Y-%m-%d')
            elif isinstance(ts, str):
                date_str = datetime.fromisoformat(ts).strftime('%Y-%m-%d')
            elif isinstance(ts, int):  # UNIX timestamp
                date_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
        except:
            pass

        formatted.append({
            'date': date_str,
            'temperature': d.get('temperature', 0),
            'rainfall': d.get('rainfall', 0)
        })

    return {'data': formatted}


@app.route('/analyst/get-alerts')
def get_alerts():
    try:
        alerts = list(mongo.db.climate_alerts.find().sort("timestamp", -1))
        for a in alerts:
            a["_id"] = str(a["_id"])
            a["timestamp"] = a["timestamp"].isoformat()
        return jsonify({"success": True, "alerts": alerts})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})



@app.route('/analyst/alerts')
def analyst_alerts():
    return render_template('analyst/analyst_alerts.html')



@app.route('/analyst/submit_feedback', methods=['POST'])
def submit_feedback_ajax():
    message = request.form.get('message')
    username = session.get('username', 'unknown')
    mongo.db.feedback.insert_one({
        'username': username,
        'message': message,
        'timestamp': datetime.datetime.now()
    })
    # ✅ Log feedback
    mongo.db.activities.insert_one({
        "username": username,
        "action": "Submitted feedback",
        "timestamp": datetime.datetime.utcnow()
    })
    return 'Success', 200

@app.route('/analyst/get-prediction-history')
def get_prediction_history():
    try:
        username = session.get("username", "unknown")
        history = list(mongo.db.prediction_history.find({"username": username}).sort("timestamp", -1))
        
        for record in history:
            record["_id"] = str(record["_id"])  # convert ObjectId to string
            record["timestamp"] = record["timestamp"].isoformat()  # make datetime JSON serializable

        return jsonify({"success": True, "history": history})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})




# --- Run the Flask application ---
if __name__ == '__main__':
    # Set debug to True for development. Disable in production.
    app.run(debug=True)
