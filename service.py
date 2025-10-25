# service.py
# This file runs as an Android service when started via the AlarmManager intent.
# It will compute monthly totals from the same SQLite DB and send a notification.

import os
import sqlite3
import datetime
import time
from plyer import notification

DB_FILE = os.path.join(os.getcwd(), 'data.db')

def load_monthly_summary_for_default_user():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        today = datetime.date.today()
        start_month = str(today.replace(day=1))
        end_month = str(today)
        c.execute('''SELECT kind, SUM(amount) FROM entries e JOIN users u ON e.user_id=u.id
                     WHERE u.name=? AND date BETWEEN ? AND ? GROUP BY kind''', ('Default', start_month, end_month))
        data = dict(c.fetchall())
        conn.close()
        income = data.get('income', 0)
        expense = data.get('expense', 0)
        return income, expense
    except Exception as e:
        print('service db error', e)
        return 0, 0

def main():
    # compute summary and notify
    income, expense = load_monthly_summary_for_default_user()
    title = 'Monthly Summary (Service)'
    msg = f'Income {income} — Expense {expense} — Net {income - expense}'
    try:
        notification.notify(title=title, message=msg, timeout=10)
    except Exception as e:
        print('notification error', e)

if __name__ == '__main__':
    main()

