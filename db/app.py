import os
import sqlite3
from functools import wraps
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for
from flask import session, flash, g, abort
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)

app.config["DATABASE"] = os.environ.get("DATABASE_URL")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
