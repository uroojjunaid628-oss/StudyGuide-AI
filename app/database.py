import os

import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv

load_dotenv()


POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_PORT = os.getenv("POSTGRES_PORT")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_DB = os.getenv("POSTGRES_DB")


def create_database():
    connection = psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        database="postgres"
    )

    connection.autocommit = True
    cursor = connection.cursor()

    cursor.execute(
        "SELECT 1 FROM pg_database WHERE datname = %s",
        (POSTGRES_DB,)
    )

    database_exists = cursor.fetchone()

    if not database_exists:
        cursor.execute(
            sql.SQL("CREATE DATABASE {}").format(
                sql.Identifier(POSTGRES_DB)
            )
        )

    cursor.close()
    connection.close()


def get_database_connection():
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        database=POSTGRES_DB
    )


def create_students_table():
    connection = get_database_connection()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id SERIAL PRIMARY KEY,
            whatsapp_number VARCHAR(30) UNIQUE NOT NULL,
            name VARCHAR(100),
            current_country VARCHAR(100),
            desired_country VARCHAR(100),
            study_level VARCHAR(100),
            program VARCHAR(150),
            previous_qualification VARCHAR(200),
            academic_score VARCHAR(100),
            english_test VARCHAR(100),
            preferred_intake VARCHAR(100),
            budget VARCHAR(100),
            webhook_status VARCHAR(30) DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.commit()
    cursor.close()
    connection.close()


if __name__ == "__main__":
    create_database()
    create_students_table()
    print("StudyGuide database and students table are ready.")

def get_student(whatsapp_number):
    connection = get_database_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            id,
            name,
            current_country,
            desired_country,
            study_level,
            program,
            previous_qualification,
            academic_score,
            english_test,
            preferred_intake,
            budget,
            webhook_status
        FROM students
        WHERE whatsapp_number = %s
        """,
        (whatsapp_number,)
    )

    student = cursor.fetchone()

    cursor.close()
    connection.close()

    if not student:
        return None

    return {
        "id": student[0],
        "name": student[1],
        "current_country": student[2],
        "desired_country": student[3],
        "study_level": student[4],
        "program": student[5],
        "previous_qualification": student[6],
        "academic_score": student[7],
        "english_test": student[8],
        "preferred_intake": student[9],
        "budget": student[10],
        "webhook_status": [11]
    }

def create_student(whatsapp_number):
    connection = get_database_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO students (whatsapp_number)
        VALUES (%s)
        ON CONFLICT (whatsapp_number) DO NOTHING
        """,
        (whatsapp_number,)
    )

    connection.commit()

    cursor.close()
    connection.close()    

def update_student(whatsapp_number, profile):
    connection = get_database_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE students
        SET
            name = %s,
            current_country = %s,
            desired_country = %s,
            study_level = %s,
            program = %s,
            previous_qualification = %s,
            academic_score = %s,
            english_test = %s,
            preferred_intake = %s,
            budget = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE whatsapp_number = %s
        """,
        (
            profile.get("name"),
            profile.get("current_country"),
            profile.get("desired_country"),
            profile.get("study_level"),
            profile.get("program"),
            profile.get("previous_qualification"),
            profile.get("academic_score"),
            profile.get("english_test"),
            profile.get("preferred_intake"),
            profile.get("budget"),
            whatsapp_number
        )
    )

    connection.commit()

    cursor.close()
    connection.close()   

def update_webhook_status(whatsapp_number, status):
    connection = get_database_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE students
        SET webhook_status = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE whatsapp_number = %s
        """,
        (status, whatsapp_number)
    )

    connection.commit()

    cursor.close()
    connection.close()    