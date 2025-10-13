# [flashcards.josh.software](https://flashcards.josh.software)

This is a web-based flashcard application designed for students to study various modules. It features a dynamic question and answer system, user authentication via Discord, and a backend powered by Flask and Supabase.

## Technology Stack

### Backend
- **Flask**: A lightweight WSGI web application framework in Python. It's used to handle routing, request processing, and to serve the frontend application.
- **Supabase**: An open-source Firebase alternative. Supabase is used for the entire backend infrastructure, including:
    - **PostgreSQL Database**: The core data storage for users, questions, modules, and all other application data. The schema is managed through SQL migration files.
    - **Storage**: Used for storing PDF files associated with questions.
    - **Serverless Functions**: Supabase's edge functions (RPC calls in the database) are used for performance-critical operations like fetching filtered data, checking for duplicate questions, and processing answers.

### Frontend
- **HTML/CSS/JavaScript**: The frontend is built with standard web technologies.
- **Jinja2**: A modern and designer-friendly templating language for Python, used by Flask to render dynamic HTML pages.
- **jQuery**: Used for simplifying DOM manipulation and handling AJAX requests.

### APIs and Services
- **Discord API**: Used for user authentication (OAuth2).
- **GitHub Sponsors**: Integrated for accepting support through GitHub Sponsors and repository starring.

## Features

- **User Authentication**: Users can log in using their Discord account.
- **Dynamic Flashcards**: Users can select a module and get questions with multiple-choice answers.
- **Smart Distractors**: The application intelligently generates distractors for questions by finding answers from other similar questions.
- **Filtering**: Questions can be filtered by topic, subtopic, and tags.
- **User Statistics**: The application tracks user performance, including correct answers, total answers, and streaks.
- **Leaderboard**: A leaderboard displays top users, which can be sorted and filtered by module.
- **PDF Access**: Users can request access to and view relevant PDF materials.
- **User Submissions**: Users can submit new flashcards and distractors for review.
- **Admin Panel**: An admin interface for reviewing and managing submitted content.
- **API for Ingestion**: A secure API endpoint allows for programmatic ingestion of flashcards, for example, from an n8n workflow.

## How It's Built

The application follows a standard Flask project structure.

- `app.py`: The main application file that initializes the Flask app, registers blueprints (routes), and sets up context processors.
- `config.py`: Manages all configuration variables, including secret keys and API credentials, loaded from a `.env` file.
- `routes/`: This directory contains the different routes for the application, separated by functionality (e.g., `main.py`, `api.py`, `auth.py`).
- `models/`: This directory contains the data models and logic for interacting with the Supabase database. `supabase_adapter.py` provides a centralized client for database operations.
- `templates/`: Contains all the Jinja2 HTML templates for the user interface.
- `static/`: Holds all the static assets like CSS, JavaScript, and images.
- `supabase/`: Contains the Supabase project configuration and database migrations.

### Supabase and API Requests

Supabase is the core of the backend. The Flask application communicates with Supabase through the `supabase-py` library.

**Local Development with Supabase CLI**: This project uses the Supabase CLI for local development rather than connecting to a remote Supabase instance. This approach provides several advantages:
- **Performance**: Local database calls are significantly faster than remote API calls, which is especially beneficial given that the application's database queries aren't fully optimized yet.
- **Cost-effective**: Running locally doesn't incur any hosting costs during development.
- **Offline development**: You can work on the project without an internet connection.
- **Easy setup**: The CLI handles all the infrastructure setup automatically.

- **Database Interaction**: The `models/database.py` and `models/supabase_adapter.py` files contain functions that query the Supabase PostgreSQL database. These functions are used to fetch modules, questions, user stats, and more.
- **API Routes**: The `routes/api.py` file defines several API endpoints that are used by the frontend to fetch data dynamically. For example, when a user selects a module, an AJAX request is made to `/api/get_filters` to populate the topic and subtopic dropdowns.
- **RPC Functions**: To optimize performance, the application makes use of PostgreSQL functions (Remote Procedure Calls) within Supabase. For instance, `get_module_filter_data_rpc` is a function in the database that efficiently fetches all filterable data for a given module in a single call, rather than multiple separate queries. This significantly reduces latency.

## Security

- **Discord Authentication**: User authentication is handled via Discord OAuth2, ensuring that users are legitimate Discord account holders. The application only requests the `identify` and `guilds` scopes, minimizing the data collected from users.
- **Access Control Whitelist**: A `whitelist.json` file manages access permissions with Discord user IDs for PDF access (`user_ids`), admin privileges (`admin_ids`), and authorized guilds (`guild_ids`). Users are automatically added to the whitelist when admins approve their access requests.
- **CSRF Protection**: Cross-Site Request Forgery protection is implemented using Flask-WTF. All forms include CSRF tokens and AJAX requests automatically include CSRF headers, preventing malicious sites from submitting forms on behalf of authenticated users.
- **Environment Variables**: All sensitive information, such as API keys and secret keys, is to be stored in a `.env` file.
- **Signed Tokens**: To prevent users from repeatedly answering the same question to boost their score, a signed token is generated for each question. This token is validated on the backend to ensure it's used only once per user for a correct answer.
- **API Key Authentication**: The data ingestion API (`/api/ingest_flashcards`) is protected by an API key, ensuring that only authorized services (like an n8n workflow) can add new content.

## Setup and Installation

To run this project locally, follow these steps:

### Prerequisites

1. **Install Node.js**: Required for the Supabase CLI. Download from [nodejs.org](https://nodejs.org/)
2. **Install Docker**: Required for local Supabase instance. Download from [docker.com](https://www.docker.com/get-started)
3. **Python 3.8+**: Required for the Flask application

### Installation Steps

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/Joshua-Wilcox/Flashcards.git
    cd Flashcards
    ```

2.  **Create a virtual environment and install dependencies:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    pip install -r requirements.txt
    ```

3.  **Install Supabase CLI:**
    ```bash
    npm install -g @supabase/cli
    ```

4.  **Create a `.env` file** in the root of the project with the following variables:

    ```env
    # Flask Configuration
    SECRET_KEY=your_very_secret_key_here
    TOKEN_SECRET_KEY=another_secret_for_tokens

    # Discord OAuth2 Credentials (get from Discord Developer Portal)
    DISCORD_CLIENT_ID=your_discord_client_id
    DISCORD_CLIENT_SECRET=your_discord_client_secret
    DISCORD_REDIRECT_URI=http://127.0.0.1:2456/callback

    # Testing Configuration (optional - for separate test Discord app)
    IS_TESTING=no
    TEST_CLIENT_ID=your_test_discord_client_id
    TEST_SECRET=your_test_discord_client_secret

    # Supabase Local Development (these will be set automatically by CLI)
    SUPABASE_URL=http://localhost:54321
    SUPABASE_ANON_KEY=your_anon_key_from_supabase_cli
    SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_from_supabase_cli
    DATABASE_URL=postgresql://postgres:postgres@localhost:54322/postgres

    # API Access (optional - for programmatic content ingestion)
    N8N_INGEST_TOKEN=your_secure_api_token

    # GitHub configuration for sponsors
    GITHUB_SPONSORS_URL=https://github.com/sponsors/Joshua-Wilcox?o=esb
    GITHUB_REPO_URL=https://github.com/Joshua-Wilcox/Flashcards
    ```

5.  **Initialize and start Supabase:**
    ```bash
    # Initialize Supabase in the project (if not already done)
    supabase init

    # Start the local Supabase stack
    supabase start
    ```

    After running `supabase start`, you'll see output with the local URLs and keys. Update your `.env` file with the `SUPABASE_ANON_KEY` and `SUPABASE_SERVICE_ROLE_KEY` values from this output.

6.  **Apply database migrations:**
    ```bash
    supabase db reset
    ```

7.  **Run the application:**
    ```bash
    # In one terminal, ensure Supabase is running
    npx supabase start

    # In another terminal, start the Flask app
    python3 app.py
    ```

    The application will be available at `http://127.0.0.1:2456`.

### Development Workflow

For daily development, you only need to run:
```bash
npx supabase start && python3 app.py
```

This will start the local Supabase instance and then launch the Flask application.

## A Note on Development

This project has been developed with the assistance of AI. I am always open to feedback and contributions. If you have any suggestions for improvements or find any issues, please feel free to open an issue or submit a pull request. Your code reviews are greatly appreciated!
