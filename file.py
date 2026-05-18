import re
import base64

from flask import Flask, request, url_for, flash, session, render_template, redirect
import sqlite3
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
import time
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

app.secret_key = '3nqnu35n34h134grfyu3hjbyuq34f'

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///vote.db'

db = SQLAlchemy(app)

migrate = Migrate(app, db)


class Users(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fullName = db.Column(db.String(40), nullable=False)
    email = db.Column(db.String(30), nullable=False, unique=True)
    password = db.Column(db.String(100), nullable=False)
    elections = db.relationship(
        'election_details', backref='creator', lazy=True)
    total_elections_made = db.Column(db.Integer, default=0)
    total_votes_cast = db.Column(db.Integer, default=0)


class Candidate(db.Model):
    cand_name = db.Column(db.String(30), nullable=False)
    cand_id = db.Column(db.String(30), primary_key=True, nullable=False)
    cand_photo = db.Column(db.LargeBinary, nullable=True)
    cand_email = db.Column(db.String(30), nullable=False)
    elec_made_id = db.Column(
        db.Integer, db.ForeignKey('users.id'), nullable=False)
    cand_election_id = db.Column(db.Integer, db.ForeignKey(
        'election_details.election_id'), nullable=False)
    cand_votes = db.Column(db.Integer, default=0)


class election_details(db.Model):
    election_id = db.Column(db.Integer, nullable=False, primary_key=True)
    title = db.Column(db.String(30), nullable=False)
    position = db.Column(db.String(30), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    start_datetime = db.Column(db.DateTime, nullable=False)
    end_datetime = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.Boolean, default=True)
    is_ongoing = db.Column(db.Boolean, default=True)
    created_by = db.Column(
        db.Integer, db.ForeignKey('users.id'), nullable=False)

    date_created = db.Column(db.DateTime, nullable=False)

    election_votes_cast = db.Column(db.Integer, default=0)

    candidates = db.relationship(
        'Candidate', backref='election', lazy=True, cascade="all, delete-orphan")  # ???THIS!!


class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    voter_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    election_id = db.Column(db.Integer, db.ForeignKey(
        'election_details.election_id'), nullable=False)
    candidate_id = db.Column(db.String(30), db.ForeignKey(
        'candidate.cand_id'), nullable=False)

    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint(
        'voter_id', 'election_id', name='unique_vote_per_user'),)
    election = db.relationship('election_details', backref='votes')
    candidate = db.relationship('Candidate', backref='votes')


with app.app_context():
    db.create_all()


@app.route('/', methods=['GET'])
def home():
    # signed_user = Users.query.filter_by().all()
    # session['logged_email'] = signed_user.email

    if 'logged_id' not in session:
        return redirect(url_for('login'))

    user = Users.query.get(session['logged_id'])

    if not user:
        session.pop('logged_id', None)
        return redirect(url_for('login'))
    search_query = request.args.get('search_query')
    print("search", search_query)
    if search_query == None or search_query == "":
        return render_template('main.html', user=user.fullName, email=user.email)
    elif search_query != "" and search_query[-1].isdigit():
        return redirect(search_query)

    else:
        flash("Please enter a valid election link", "fail")
        return redirect(url_for('home'))


@app.route('/create_election', methods=['POST', 'GET'])  # *Unfinished
def create_election():

    if 'logged_id' not in session:
        return redirect(url_for('login'))
    user = Users.query.get(session['logged_id'])

    if not user:
        session.pop('logged_id', None)
        return redirect(url_for('login'))

    if request.method == 'POST':
        election_title = request.form.get('election_title')
        position = request.form.get('position')
        description = request.form.get('description')
        start_datetime_str = request.form.get('start_datetime')
        end_datetime_str = request.form.get('end_datetime')

        if 'send_notifications' in request.form:
            send_notifications = True
        else:
            send_notifications = False

        start_datetime = datetime.strptime(
            start_datetime_str,  "%Y-%m-%dT%H:%M")
        end_datetime = datetime.strptime(end_datetime_str, "%Y-%m-%dT%H:%M")

        existing_election = election_details.query.filter_by(
            title=election_title).first()

        if existing_election:
            flash("Election title already exists, choose a different title", "fail")
            return redirect(url_for('create_election'))

        now = datetime.now()
        new_election = election_details(created_by=user.id, title=election_title, position=position,
                                        description=description, end_datetime=end_datetime, start_datetime=start_datetime, date_created=now)

        db.session.add(new_election)
        db.session.commit()

        cand_name = request.form.getlist('candidate_name')
        cand_id = request.form.getlist('candidate_id')
        cand_photo = request.files.getlist('candidate_photo')
        cand_email = request.form.getlist('candidate_email')
        for name, c_id, photo, email in zip(cand_name, cand_id, cand_photo, cand_email):

            photo_data = None
            if photo:
                photo_data = photo.read()
            else:
                photo_data = None

            new_candidates = Candidate(cand_name=name, cand_election_id=new_election.election_id,
                                       cand_id=c_id, cand_email=email, cand_photo=photo_data, elec_made_id=user.id)
            db.session.add(new_candidates)

        db.session.commit()

        user.total_elections_made += 1
        db.session.commit()

        # ? if election_title - Check if election title is active

        # VARIABLES:

        flash("Election created successfully", "success")
        return redirect(url_for('manage_election'))

    return render_template('create_election.html')


@app.route('/manage_election', methods=['POST', 'GET'])
def manage_election():
    duration = 4
    dur_time = time.time()
    is_active = True

    #!Active election
    if 'logged_id' not in session:
        return redirect(url_for('login'))
    user = Users.query.get(session['logged_id'])

    num_cand = Candidate.query.filter_by(elec_made_id=user.id).count()
    if not user:
        session.pop('logged_id', None)
        return redirect(url_for('login'))

    elections = election_details.query.filter_by(created_by=user.id).all()

    active_elec = 0
    ended = 0
    # num_cand = Candidate.query.filter_by(elec_made_id=user.id).count()
    now = datetime.now()
    # formatted_now = now.strftime("%Y-%m-%dT%H:%M")
    for election in elections:
        if election.status == True:
            active_elec += 1
            is_active = True
        else:
            is_active = False
        if election.is_ongoing == False:
            ended += 1

        if election.end_datetime < now:
            election.status = False
            election.is_ongoing = False
        else:
            election.status = True
    if request.method == 'POST':
        search_query = request.form.get('search_query', '').lower()
        filtered_elections = []
        for election in elections:
            if search_query in election.title.lower() or search_query in election.position.lower():
                filtered_elections.append(election)

        elections = filtered_elections

    db.session.commit()

    return render_template('manage_election.html', elections=elections, num_cand=num_cand, number_of_elec=user.total_elections_made, active_elec=active_elec, ended=ended, is_active=is_active)


@app.route('/see_election')
def see_election():
    if 'logged_id' not in session:
        return redirect(url_for('login'))

    user = Users.query.get(session['logged_id'])

    votes = Vote.query.filter_by(voter_id=user.id).all()

    election_ids = [vote.election_id for vote in votes]

    elections = election_details.query.filter(
        election_details.election_id.in_(election_ids)
    ).all()
    # candidates = elections.candidates

    for election in elections:
        for candidate in election.candidates:
            if candidate.cand_photo:
                candidate.photo_data = base64.b64encode(
                    candidate.cand_photo).decode('utf-8')
                
            
    return render_template('see_election_result.html', elections=elections, user=user, votes=votes)

@app.route('/election_result/<int:election_id>')
def election_result(election_id):
    if 'logged_id' not in session:
        return redirect(url_for('login'))

    election = election_details.query.get_or_404(election_id)
    votes = Vote.query.filter_by(election_id=election_id).all()

    now = datetime.now().strftime("%b %d, %Y")

    # Find winner safely
    candidates = election.candidates
    candidates = sorted(candidates, key=lambda c: c.cand_votes, reverse=True) 
    winner = max(candidates, key=lambda c: c.cand_votes) if candidates else None 

    # Prepare photos
    for candidate in candidates:
        if candidate.cand_photo:
            candidate.photo_data = base64.b64encode(
                candidate.cand_photo
            ).decode('utf-8')
        if election.election_votes_cast > 0:
            total_votes = election.election_votes_cast
            candidate.percentage = round(
                    (candidate.cand_votes / total_votes) * 100)
        else:
            candidate.percentage = 0.0

    return render_template(
        'election_result.html',
        election=election,
        votes=votes,
        winner=winner,
        now=now
    )

@app.route('/archived_election')
def archived_election():
    if 'logged_id' not in session:
        return redirect(url_for('login'))

    return redirect(url_for('page_not_found'))


@app.route('/signup', methods=['POST', 'GET'])
def sign_up():
    if request.method == 'POST':
        fullName = request.form.get('fullName')
        email = request.form.get('email')
        pwd = request.form.get('password')
        password = generate_password_hash(pwd)
        confirmPassword = request.form.get('confirmPassword')
        signed_users = Users.query.filter_by(email=email).first()
        if confirmPassword != pwd:
            flash("Passwords don't match", "fail")
            return redirect(url_for('sign_up'))
        elif signed_users:
            flash("User already exists", 'fail')
            return redirect(url_for('sign_up'))
        else:
            flash("Sign up successful", "success")
            details = Users(fullName=fullName, email=email, password=password)
            db.session.add(details)
            db.session.commit()
            next_page = request.form.get('next') or request.args.get('next')
            if next_page and next_page != 'None':
                return redirect(next_page)
            return redirect(url_for('login'))
    return render_template('sign_up.html', next=request.args.get('next'))


@app.route('/login', methods=['POST', 'GET'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        signed_users = Users.query.filter_by(email=email).first()
        if signed_users and check_password_hash(signed_users.password, password):
            flash("Login successful", 'success')
            session['logged_id'] = signed_users.id
            next_page = request.form.get('next') or request.args.get('next')
            if next_page and next_page != 'None':
                return redirect(next_page)
            return redirect(url_for('home'))
        elif not signed_users:
            flash("User doesn't exist", 'fail')
            return redirect(url_for('login'))
        else:
            flash("Invalid details", 'fail')
            return redirect(url_for('login'),  next=request.args.get('next'))

    return render_template('login.html')


@app.route('/terms_and_conditions')
def terms():
    return render_template('terms.html')


@app.route('/logout')
def logout():
    session.pop('logged_id', None)
    return redirect(url_for('home'))


@app.route('/delete_election/<int:election_id>')
def delete_election(election_id):
    user = Users.query.get(session['logged_id'])
    if 'logged_id' not in session and user.id != election_details.query.get(election_id).created_by:
        return redirect(url_for('login'))
    election = election_details.query.get(election_id)

    if election and election.created_by == user.id:
        db.session.delete(election)
        db.session.commit()
        flash("Election deleted successfully", "success")
    else:
        flash("Election not found", "fail")

    return redirect(url_for('manage_election'))


@app.route('/end_election/<int:election_id>')
def end_election(election_id):
    user = Users.query.get(session['logged_id'])
    if 'logged_id' not in session and user.id != election_details.query.get(election_id).created_by:
        return redirect(url_for('login'))
    election = election_details.query.get(election_id)

    if election and election.created_by == user.id:
        election.status = False
        election.is_ongoing = False
        db.session.commit()
        flash("Election ended successfully", "success")
    else:
        flash("Election not found", "fail")

    return redirect(url_for('manage_election'))


@app.route('/vote/<int:election_id>', methods=['POST', 'GET'])
def vote(election_id):
    if 'logged_id' not in session:
        return redirect(url_for('login', next=request.url))

    voter = Users.query.get(session['logged_id'])

    election = election_details.query.get_or_404(election_id)
    now = datetime.now()

    if now < election.start_datetime or now > election.end_datetime:
        return redirect(url_for('election_status', election_id=election_id))

    existing_vote = Vote.query.filter_by(
        voter_id=voter.id, election_id=election_id).first()
    has_voted = bool(existing_vote)

    if existing_vote:
        return redirect(url_for('already_voted'))
    if request.method == 'POST':

        candidate_id = request.form.get('candidate_id')

        # Security: make sure candidate belongs to this election
        candidate = Candidate.query.filter_by(
            cand_id=candidate_id,
            cand_election_id=election_id
        ).first()

        if not candidate:
            flash("Invalid candidate selection.", "fail")
            return redirect(url_for('home'))

        new_vote = Vote(
            voter_id=voter.id,
            election_id=election_id,
            candidate_id=candidate_id, timestamp=datetime.now()
        )

        db.session.add(new_vote)
        db.session.commit()

        voter.total_votes_cast += 1
        election.election_votes_cast += 1
        candidate.cand_votes += 1
        db.session.commit()
        flash("Vote submitted successfully!", "success")
        return redirect(url_for('home'))

    candidates = election.candidates

    for candidate in candidates:
        if candidate.cand_photo:
            candidate.photo_data = base64.b64encode(
                candidate.cand_photo).decode('utf-8')
    total_votes = Vote.query.filter_by(election_id=election_id).count()
    db.session.commit()
    return render_template('vote.html', election=election, candidates=candidates, total_votes=total_votes, voter=voter, has_voted=has_voted)


@app.route('/election_status/<int:election_id>')
def election_status(election_id):
    if 'logged_id' not in session:
        return redirect(url_for('login', next=request.url))

    election = election_details.query.get_or_404(election_id)
    now = datetime.now()

    # Determine status message and date to display
    if now < election.start_datetime:
        status = "not_started"
        display_date = election.start_datetime.strftime(
            "%A, %d %B %Y at %I:%M %p")
    elif now > election.end_datetime:
        status = "ended"
        display_date = election.end_datetime.strftime(
            "%A, %d %B %Y at %I:%M %p")
    else:
        # Election is ongoing, you might redirect to vote page instead
        return redirect(url_for('vote', election_id=election_id))
    total_votes = Vote.query.filter_by(election_id=election_id).count()
    return render_template('election_status.html', election=election, status=status, display_date=display_date, total_votes=total_votes)


@app.route('/already_voted')
def already_voted():
    return render_template('already_voted.html')


@app.route('/edit_election/<int:election_id>', methods=['POST', 'GET'])
def edit_election(election_id):
    user = Users.query.get(session['logged_id'])
    if 'logged_id' not in session and user.id != election_details.query.get(election_id).created_by:
        return redirect(url_for('login'))
    election = election_details.query.get_or_404(election_id)
    candidates = election.candidates

    # Prepare candidate photos for display
    for candidate in candidates:
        if candidate.cand_photo:
            candidate.photo_data = base64.b64encode(
                candidate.cand_photo).decode('utf-8')

    if request.method == 'POST':
        # Update election details
        election.title = request.form.get('election_title')
        election.position = request.form.get('position')
        election.description = request.form.get('description')
        election.start_datetime = datetime.strptime(
            request.form.get('start_datetime'), "%Y-%m-%dT%H:%M")
        election.end_datetime = datetime.strptime(
            request.form.get('end_datetime'), "%Y-%m-%dT%H:%M")

        # Update or add candidates
        cand_name = request.form.getlist('candidate_name')
        cand_id = request.form.getlist('candidate_id')
        cand_photo = request.files.getlist('candidate_photo')
        cand_email = request.form.getlist('candidate_email')

        for name, c_id, photo, email in zip(cand_name, cand_id, cand_photo, cand_email):
            candidate = Candidate.query.filter_by(
                cand_id=c_id, cand_election_id=election.election_id).first()
            photo_data = photo.read() if photo else None

            if candidate:
                candidate.cand_name = name
                candidate.cand_email = email
                if photo_data:
                    candidate.cand_photo = photo_data
            else:
                new_candidate = Candidate(cand_name=name, cand_id=c_id, cand_email=email,
                                          cand_photo=photo_data, cand_election_id=election.election_id, elec_made_id=user.id)
                db.session.add(new_candidate)

        db.session.commit()
        flash('Election edited successfully', 'success')
        return redirect(url_for('manage_election'))

    return render_template('edit_election.html', election=election, candidates=candidates)


@app.route('/view_election/<int:election_id>', methods=['POST', 'GET'])
def view_election(election_id):
    user = Users.query.get(session['logged_id'])
    if 'logged_id' not in session and user.id != election_details.query.get(election_id).created_by:
        return redirect(url_for('login'))
    
    

    election = election_details.query.get_or_404(election_id)
    candidates = election.candidates
    for candidate in candidates:
        if candidate.cand_photo:
            candidate.photo_data = base64.b64encode(
                candidate.cand_photo).decode('utf-8')
    percentage = 0
    total_votes = election.election_votes_cast
    for candidate in candidates:
        if total_votes > 0:
            candidate.percentage = round(
                (candidate.cand_votes / total_votes) * 100)
        else:
            candidate.percentage = 0.0

    now = datetime.now()

    return render_template('view_election.html', election=election, candidates=candidates, now=now)


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404



if __name__ == "__main__":
    app.run(debug=True)