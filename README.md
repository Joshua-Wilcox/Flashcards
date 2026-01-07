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

## A Note on Development

This project has been developed with the assistance of AI. I am always open to feedback and contributions. If you have any suggestions for improvements or find any issues, please feel free to open an issue or submit a pull request. Your code reviews are greatly appreciated!
