from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import pandas as pd
from datetime import datetime
import os
from flask import send_from_directory

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'my_fixed_secret_key')

logins = {
    "admin": "123",
    "sem1": "s1",
    "sem2": "s2",
    "sem3": "s3",
    "sem4": "s4",
    "sem5": "s5",
    "sem6": "s6",
}

@app.route('/', methods=['GET', 'POST'])
def login():
    """Handles user login."""
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()

        if username in logins and logins[username] == password:
            session['user'] = username
            if username == 'admin':
                session['role'] = 'admin'
            else:
                session['role'] = 'semester_user'
                session['semester'] = username  # Store semester info

            return redirect(url_for('sem_selection'))
        
        return render_template('login.html', error="Invalid login credentials.")

    return render_template('login.html')


@app.route('/fetch_data/<semester>')
def fetch_data(semester):
    if 'user' not in session:
        return "Unauthorized! Please log in.", 403

    role = session.get('role')
    user_semester = session.get('semester')

    # ✅ Restrict access
    if role != 'admin' and user_semester != semester:
        return "Unauthorized! You are not allowed to access this data.", 403

    data = get_data_for_semester(semester)
    return jsonify(data)


def get_data_for_semester(semester):
    """Fetches data for a specific semester from Excel file."""
    try:
        df = pd.read_excel('student_fees.xlsx', sheet_name=semester, dtype=str)

        # Convert Fee columns to numeric
        df['Total Fee'] = pd.to_numeric(df['Total Fee'], errors='coerce').fillna(0).astype(int)
        df['Fee Paid'] = pd.to_numeric(df['Fee Paid'], errors='coerce').fillna(0).astype(int)

        # Compute "Fee Pending"
        df['Cumulative Paid'] = df.groupby('Register No')['Fee Paid'].cumsum()
        df['Updated Total Fee'] = df.groupby('Register No')['Total Fee'].transform('max')
        df['Fee Pending'] = df['Updated Total Fee'] - df['Cumulative Paid']
        df['Remark'] = df['Fee Pending'].apply(lambda x: "✔️" if x == 0 else "❌")

        # Convert Date
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Date'])  # Remove invalid dates
        df['Date'] = df['Date'].dt.strftime('%d-%m-%Y')

        return df.to_dict(orient='records')  # Convert to JSON for API response

    except Exception as e:
        return {"error": f"Error loading data for {semester}: {str(e)}"}



@app.route('/sem_selection', methods=['GET'])
def sem_selection():
    """Displays semester selection page."""
    if 'user' not in session:
        return redirect(url_for('login'))

    is_admin = session.get('role') == 'admin'
    semesters = ['sem1', 'sem2', 'sem3', 'sem4', 'sem5', 'sem6']
    
    return render_template('sem_selection.html', semesters=semesters, is_admin=is_admin)

from datetime import datetime

@app.route('/view_sem/<sem>', methods=['GET'])
def view_sem(sem):
    if 'user' not in session:
        return redirect(url_for('login'))

    role = session.get('role')
    user_semester = session.get('semester')

    # ✅ Restrict access: Admin can access all, semester users only their own
    if role != 'admin' and user_semester != sem:
        return render_template('error.html', message="Unauthorized! You are not allowed to access this data."), 403

    search_query = request.args.get('query', '').strip().lower()
    search_date = request.args.get('date', '').strip().lower()

    try:
        df = pd.read_excel('student_fees.xlsx', sheet_name=sem, dtype=str)

        # Convert Fee columns to numeric
        df['Total Fee'] = pd.to_numeric(df['Total Fee'], errors='coerce').fillna(0).astype(int)
        df['Fee Paid'] = pd.to_numeric(df['Fee Paid'], errors='coerce').fillna(0).astype(int)

        # ✅ Compute "Total Fee" dynamically based on installments
        df['Cumulative Paid'] = df.groupby('Register No')['Fee Paid'].cumsum()
        df['Updated Total Fee'] = df.groupby('Register No')['Total Fee'].transform('max')  
        df['Fee Pending'] = df['Updated Total Fee'] - df['Cumulative Paid']
        df['Remark'] = df['Fee Pending'].apply(lambda x: "✔️" if x == 0 else "❌")

        # ✅ Convert Date & Extract Month Name
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Date'])  # Remove invalid dates
        df['Date'] = df['Date'].dt.strftime('%d-%m-%Y')  # Keep original format
        df['Month Name'] = df['Date'].apply(lambda x: datetime.strptime(x, "%d-%m-%Y").strftime('%B').lower())  # Extract full month

        # ✅ Apply Filters
        if search_query:
            df = df[df.apply(lambda row: search_query in str(row.to_dict()).lower(), axis=1)]
        if search_date:
            month_match = [m.lower() for m in ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]]
            matched_months = [m for m in month_match if search_date in m]  # Find matching months
            if matched_months:
                df = df[df['Month Name'].isin(matched_months)]
            else:
                df = df[df['Date'] == search_date]  # Strict date search if no month match

        data = df.to_dict('records')

        return render_template('view_sem.html', sem=sem, data=data, search_query=search_query, search_date=search_date)
    except Exception as e:
        return render_template('error.html', message=f"Error loading data: {str(e)}"), 500





@app.route('/search_students', methods=['GET'])
def search_students():
    if 'user' not in session:
        return redirect(url_for('login'))

    search_query = request.args.get('query', '').strip().lower()
    all_semesters = ['sem1', 'sem2', 'sem3', 'sem4', 'sem5', 'sem6']
    combined_data = []  # Store data from all semesters

    try:
        # Load data from all semester sheets
        for sem in all_semesters:
            try:
                df = pd.read_excel('student_fees.xlsx', sheet_name=sem, dtype=str)

                # Convert Fee columns to numeric
                df['Total Fee'] = pd.to_numeric(df['Total Fee'], errors='coerce').fillna(0).astype(int)
                df['Fee Paid'] = pd.to_numeric(df['Fee Paid'], errors='coerce').fillna(0).astype(int)

                # Compute "Fee Pending"
                df['Cumulative Paid'] = df.groupby('Register No')['Fee Paid'].cumsum()
                df['Updated Total Fee'] = df.groupby('Register No')['Total Fee'].transform('max')
                df['Fee Pending'] = df['Updated Total Fee'] - df['Cumulative Paid']
                df['Remark'] = df['Fee Pending'].apply(lambda x: "✔️" if x == 0 else "❌")

                # Convert Date & Extract Month Name
                df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
                df = df.dropna(subset=['Date'])  # Remove invalid dates
                df['Date'] = df['Date'].dt.strftime('%d-%m-%Y')  # Keep original format
                df['Month Name'] = df['Date'].apply(lambda x: datetime.strptime(x, "%d-%m-%Y").strftime('%B').lower())

                # Add semester information
                df['Semester'] = sem

                combined_data.append(df)  # Store each semester's data

            except Exception as e:
                print(f"Error reading {sem}: {e}")  # Log any errors per semester

        # Combine all semester data
        if not combined_data:
            return render_template('error.html', message="No data available"), 500

        df_all = pd.concat(combined_data, ignore_index=True)

        # Apply Search Filters
        if search_query:
            df_all = df_all[df_all.apply(lambda row: search_query in str(row.to_dict()).lower(), axis=1)]

        data = df_all.to_dict('records')

        return render_template('search_results.html', data=data, search_query=search_query)

    except Exception as e:
        return render_template('error.html', message=f"Error loading data: {str(e)}"), 500




@app.route('/styles.css')
def serve_css():
    return send_from_directory('.', 'styles.css')


@app.route('/logout')
def logout():
    """Logs out the current user."""
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)  # Prevent double restart
