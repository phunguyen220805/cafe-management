import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("APP_ENV", "development")

from app import create_app


app = create_app()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        app.cli.main(args=sys.argv[1:])
    else:
        app.run(debug=True)