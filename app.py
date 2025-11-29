# app.py
from flask import Flask
from routes import bp 

app = Flask(__name__)
app.secret_key = "pro_explorer_super_secret"

app.register_blueprint(bp)

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    # Optimized for threaded performance
    app.run(host="0.0.0.0", port=port, threaded=True, debug=True, use_reloader=False)