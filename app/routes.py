import os
import secrets
from openai import OpenAI
from datetime import datetime
from PIL import Image
from flask import render_template, url_for, flash, redirect, request, abort, jsonify
from app.forms import LoginForm, RegistrationForm, UpdateAccountForm, PostForm, RequestResetForm, ResetPasswordForm, \
    ProblemForm
from app import app, db, bcrypt, mail, AUTHORIZED_USERNAMES
from app.models import User, Post, Problem
from flask_login import login_user, current_user, logout_user, login_required
from flask_mail import Message


@app.route('/')
@app.route('/home')
def home():
    page = request.args.get('page', 1, type=int)
    posts = Post.query.order_by(Post.date_posted.desc()).paginate(page=page, per_page=5)
    return render_template("index.html", posts=posts)


@app.route('/about')
def about():
    return render_template("about.html", title="About")


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(username=form.username.data, email=form.email.data, password=hashed_password)
        db.session.add(user)
        db.session.commit()
        flash(f"Account created for {form.username.data}! You are now able to log in.", "success")
        return redirect(url_for('login'))
    return render_template("register.html", Title="Registration", form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('home'))
        else:
            flash(f"Invalid login. Please check e-mail and password.", category="danger")
    return render_template('login.html', Title="Login", form=form)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))


def save_picture(form_picture):
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(app.root_path, 'static/profile_pics', picture_fn)

    # This resizes our image to 125, 125 to take up less space, rather than saving it as the original size.
    output_size = (125, 125)
    i = Image.open(form_picture)
    i.thumbnail(output_size)
    i.save(picture_path)

    # This deletes the old profile picture, but not the default one. Saves up on space.
    prev_picture = os.path.join(app.root_path, 'static/profile_pics', current_user.image_file)
    if os.path.exists(prev_picture) and os.path.basename(prev_picture) != 'default.jpg':
        os.remove(prev_picture)

    return picture_fn


@app.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    form = UpdateAccountForm()
    if form.validate_on_submit():
        if form.picture.data:
            picture_file = save_picture(form.picture.data)
            current_user.image_file = picture_file
        current_user.username = form.username.data
        current_user.email = form.email.data
        db.session.commit()
        flash(f"Your account has been updated!", category="success")
        return redirect(url_for('account'))
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.email.data = current_user.email
    image_file = url_for('static', filename='profile_pics/' + current_user.image_file)
    return render_template('account.html', Title="Account", image_file=image_file, form=form)


@app.route('/post/new', methods=['GET', 'POST'])
@login_required
def new_post():
    form = PostForm()
    if form.validate_on_submit():
        post = Post(title=form.title.data, content=form.post_content.data, author=current_user)
        db.session.add(post)
        db.session.commit()
        flash(f"Your post has been created!", category="success")
        return redirect(url_for('home'))
    return render_template('create_post.html', Title="New Post", form=form, legend='New Post')


@app.route('/post/<int:post_id>')
def post(post_id):
    get_post = Post.query.get_or_404(post_id)
    return render_template('post.html', title=get_post.title, posts=get_post)


@app.route('/post/<int:post_id>/update', methods=['GET', 'POST'])
@login_required
def update_post(post_id):
    get_post = Post.query.get_or_404(post_id)
    if get_post.author != current_user:
        abort(403)
    form = PostForm()
    if form.validate_on_submit():
        get_post.title = form.title.data
        get_post.content = form.post_content.data
        get_post.date_posted = datetime.utcnow()
        db.session.commit()
        flash(f"Your post has been updated!", category="success")
        return redirect(url_for('post', post_id=get_post.id))
    elif request.method == 'GET':
        form.title.data = get_post.title
        form.post_content.data = get_post.content
    return render_template('create_post.html', title='Update Post', form=form, legend='Update Post')


@app.route('/post/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id):
    get_post = Post.query.get_or_404(post_id)
    if get_post.author != current_user:
        abort(403)
    db.session.delete(get_post)
    db.session.commit()
    flash(f"Your post has been deleted!", category="success")
    return redirect(url_for('home'))


@app.route('/user/<string:username>')
def user_post(username):
    page = request.args.get('page', 1, type=int)
    user = User.query.filter_by(username=username).first_or_404()
    get_user_post = Post.query.filter_by(author=user) \
        .order_by(Post.date_posted.desc()) \
        .paginate(page=page, per_page=5)
    return render_template('user_post.html', posts=get_user_post, user=user)


def send_reset_email(user):
    token = user.get_reset_token()
    msg = Message('Password Reset Request', sender='noreply@gmail.com', recipients=[user.email])
    msg.body = f'''To reset your password, visit the following link:
{url_for('reset_token', token=token, _external=True)}
If you did not make this request then simply ignore this.
    '''
    mail.send(msg)


@app.route('/reset_password', methods=['GET', 'POST'])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = RequestResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        send_reset_email(user)
        flash('An E-mail has been sent with instructions to reset your password.', category='info')
        return redirect(url_for('login'))
    return render_template('reset_request.html', title='Reset Password', form=form)


@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    user = User.verify_reset_token(token)
    if user is None:
        flash('Invalid or Expired Token', category='warning')
        return redirect(url_for('reset_request'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user.password = hashed_password
        db.session.commit()
        flash(f"Your password has been updated!", "success")
        return redirect(url_for('login'))
    return render_template('reset_token.html', title='Reset Password', form=form)


client = OpenAI(api_key=app.config['CHATBOT_KEY'])


@app.route('/bot')
def bot():
    return render_template('bot.html')


chat_history: list
chat_history = []


@app.route('/chatbot', methods=['POST'])
def chatbot():
    if request.method == 'POST':
        # Get the message from the user
        user_input = request.form["message"]

        # Using the OpenAI API to generate a response
        prompt = f"The user: {user_input}\nChatBot: "
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a Python-teaching assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )

        # Extracting the response
        bot_response = response.choices[0].message.content

        # Adding the last message send by the user
        chat_history.append(f"User: {user_input}\nChatBot: {bot_response}")

        return jsonify({"bot_response": bot_response, "user_input": user_input})


@app.route('/coding')
def coding():
    page = request.args.get('page', 1, type=int)
    problems = Problem.query.order_by(Problem.date_posted.desc()).paginate(page=page, per_page=5)
    return render_template('coding_hub.html', problems=problems)


@app.route("/coding/new", methods=['GET', 'POST'])
@login_required
def new_problem():
    if current_user.username not in AUTHORIZED_USERNAMES:
        abort(403)  # Forbidden
    form = ProblemForm()
    if form.validate_on_submit():
        problem = Problem(title=form.title.data, content=form.content.data, result=form.result.data,
                          author=current_user)
        db.session.add(problem)
        db.session.commit()
        flash('Your problem has been created!', 'success')
        return redirect(url_for('coding'))
    return render_template('create_problem.html', title='New Problem', form=form, legend='New Problem')


@app.route('/coding/<string:username>')
def user_problem(username):
    page = request.args.get('page', 1, type=int)
    user = User.query.filter_by(username=username).first_or_404()
    get_user_problem = Problem.query.filter_by(author=user) \
        .order_by(Problem.date_posted.desc()) \
        .paginate(page=page, per_page=5)
    return render_template('user_problem.html', problem=get_user_problem, user=user)


@app.route('/coding/<int:problem_id>')
def problem(problem_id):
    get_problem = Problem.query.get_or_404(problem_id)
    return render_template('problem.html', title=get_problem.title, problem=get_problem)


@app.route('/problem/<int:problem_id>/update', methods=['GET', 'POST'])
@login_required
def update_problem(problem_id):
    get_problem = Problem.query.get_or_404(problem_id)
    if get_problem.author != current_user:
        abort(403)
    form = ProblemForm()
    if form.validate_on_submit():
        get_problem.title = form.title.data
        get_problem.content = form.content.data
        get_problem.result = form.result.data
        get_problem.date_posted = datetime.utcnow()
        db.session.commit()
        flash("Your problem has been updated!", category="success")
        return redirect(url_for('problem', problem_id=get_problem.id))
    elif request.method == 'GET':
        form.title.data = get_problem.title
        form.content.data = get_problem.content
    return render_template('create_problem.html', title='Update Problem', form=form, legend='Update Problem')


@app.route('/playground')
def playground():
    admin_title_post = "Welcome to PyRo Playground!"
    admin_content_post = ("Here is PyRo Academy's Playground! Here you can run any Python code, with no restrictions. "
                          "Feel free to experiment with anything you would like. There are no limits. ")
    return render_template('playground.html', title=admin_title_post, post_content=admin_content_post)


@app.route('/receive_output', methods=['POST'])
def receive_output():
    data = request.get_json()
    output = data.get('output')
    problem_id = data.get('problem_id')

    testing_problem = Problem.query.get(problem_id)
    if testing_problem.result != output:
        flash("Your result is not correct, but do not worry, that's how everyone learns. Just try again!", category='danger')
    flash("Great! Your result is correct.", category='success')

    return jsonify({'status': 'success', 'received_output': output, 'problem_id': problem_id})
