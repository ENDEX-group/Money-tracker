# main.py
from kivy.config import Config
Config.set('kivy', 'keyboard_mode', 'systemandmulti')

from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import StringProperty, ListProperty
from kivy.storage.jsonstore import JsonStore
from kivy.metrics import dp
from kivy.utils import platform
from kivy.app import App

from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.list import OneLineListItem, MDList
from kivymd.uix.textfield import MDTextField
from kivymd.uix.dialog import MDDialog
from kivymd.uix.picker import MDDatePicker

import sqlite3
import datetime
import os
import traceback

# plyer for notifications (works on many platforms)
from plyer import notification

KV = '''
ScreenManager:
    DashboardScreen:
    AddEntryScreen:
    HistoryScreen:

<DashboardScreen>:
    name: 'dashboard'
    MDBoxLayout:
        orientation: 'vertical'
        MDTopAppBar:
            title: 'Family Expense Tracker'
            left_action_items: [['menu', lambda x: app.open_users_dialog()]]
            right_action_items: [['plus', lambda x: root.manager.current='add']]
        MDBoxLayout:
            padding: dp(12)
            spacing: dp(12)
            orientation: 'vertical'
            MDCard:
                size_hint_y: None
                height: dp(140)
                padding: dp(12)
                MDBoxLayout:
                    orientation: 'vertical'
                    MDLabel:
                        text: root.greeting
                        halign: 'left'
                        font_style: 'H5'
                    MDLabel:
                        text: root.selected_user_display
                        halign: 'left'
                        theme_text_color: 'Secondary'
            MDBoxLayout:
                size_hint_y: None
                height: dp(220)
                spacing: dp(12)
                MDCard:
                    padding: dp(12)
                    MDBoxLayout:
                        orientation: 'vertical'
                        MDLabel:
                            text: 'Today'
                            font_style: 'Subtitle1'
                        MDLabel:
                            text: root.today_summary
                            font_style: 'H6'
                MDCard:
                    padding: dp(12)
                    MDBoxLayout:
                        orientation: 'vertical'
                        MDLabel:
                            text: 'This Month'
                            font_style: 'Subtitle1'
                        MDLabel:
                            text: root.month_summary
                            font_style: 'H6'
            MDCard:
                padding: dp(12)
                MDBoxLayout:
                    orientation: 'horizontal'
                    MDRaisedButton:
                        text: 'History'
                        on_release: root.manager.current='history'
                    MDFlatButton:
                        text: 'Refresh'
                        on_release: app.refresh_all()

<AddEntryScreen>:
    name: 'add'
    MDBoxLayout:
        orientation: 'vertical'
        MDTopAppBar:
            title: 'Add Income/Expense'
            left_action_items: [['arrow-left', lambda x: root.manager.current='dashboard']]
        MDBoxLayout:
            padding: dp(12)
            spacing: dp(12)
            orientation: 'vertical'
            MDTextField:
                id: amount
                hint_text: 'Amount'
                input_filter: 'float'
                required: True
            MDTextField:
                id: category
                hint_text: 'Category (e.g., Food, Salary, Rent)'
            MDTextField:
                id: note
                hint_text: 'Note (optional)'
            MDBoxLayout:
                size_hint_y: None
                height: dp(48)
                MDRaisedButton:
                    text: 'Pick Date'
                    on_release: app.show_date_picker()
                MDLabel:
                    id: date_label
                    text: root.chosen_date
                    halign: 'left'
            MDBoxLayout:
                size_hint_y: None
                height: dp(48)
                MDRaisedButton:
                    text: 'Income'
                    on_release: app.save_entry('income')
                MDFlatButton:
                    text: 'Expense'
                    on_release: app.save_entry('expense')

<HistoryScreen>:
    name: 'history'
    MDBoxLayout:
        orientation: 'vertical'
        MDTopAppBar:
            title: 'History'
            left_action_items: [['arrow-left', lambda x: root.manager.current='dashboard']]
        ScrollView:
            MDList:
                id: history_list
'''

DB_FILE = 'data.db'


class DashboardScreen(MDScreen):
    greeting = StringProperty('Welcome!')
    selected_user_display = StringProperty('')
    today_summary = StringProperty('')
    month_summary = StringProperty('')


class AddEntryScreen(MDScreen):
    chosen_date = StringProperty(str(datetime.date.today()))


class HistoryScreen(MDScreen):
    pass


class ExpenseDB:
    def __init__(self, db_path=DB_FILE):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        c = self.conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                kind TEXT,
                amount REAL,
                category TEXT,
                note TEXT,
                date TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        self.conn.commit()

    def add_user(self, name):
        c = self.conn.cursor()
        try:
            c.execute('INSERT OR IGNORE INTO users(name) VALUES(?)', (name,))
            self.conn.commit()
            c.execute('SELECT id FROM users WHERE name=?', (name,))
            r = c.fetchone()
            return r[0] if r else None
        except Exception as e:
            print('add_user error', e)
            return None

    def get_user_by_name(self, name):
        c = self.conn.cursor()
        c.execute('SELECT id,name FROM users WHERE name=?', (name,))
        return c.fetchone()

    def list_users(self):
        c = self.conn.cursor()
        c.execute('SELECT name FROM users ORDER BY name')
        return [r[0] for r in c.fetchall()]

    def add_entry(self, user_name, kind, amount, category, note, date_text):
        user = self.get_user_by_name(user_name)
        if not user:
            uid = self.add_user(user_name)
        else:
            uid = user[0]
        c = self.conn.cursor()
        c.execute('INSERT INTO entries(user_id, kind, amount, category, note, date) VALUES(?,?,?,?,?,?)',
                  (uid, kind, amount, category, note, date_text))
        self.conn.commit()

    def get_entries_for_user(self, user_name):
        c = self.conn.cursor()
        c.execute('''SELECT e.id, u.name, e.kind, e.amount, e.category, e.note, e.date
                     FROM entries e JOIN users u ON e.user_id=u.id
                     WHERE u.name=? ORDER BY e.date DESC''', (user_name,))
        return c.fetchall()

    def sum_for_user_between(self, user_name, start_date, end_date):
        c = self.conn.cursor()
        c.execute('''SELECT kind, SUM(amount) FROM entries e JOIN users u ON e.user_id=u.id
                     WHERE u.name=? AND date BETWEEN ? AND ? GROUP BY kind''', (user_name, start_date, end_date))
        return dict(c.fetchall())

    def meta_get(self, key, default=None):
        c = self.conn.cursor()
        c.execute('SELECT value FROM meta WHERE key=?', (key,))
        r = c.fetchone()
        return r[0] if r else default

    def meta_set(self, key, value):
        c = self.conn.cursor()
        c.execute('INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)', (key, str(value)))
        self.conn.commit()


class FamilyExpenseApp(MDApp):
    users = ListProperty([])

    def build(self):
        self.title = 'Family Expense Tracker'
        self.db = ExpenseDB()
        self.store = JsonStore('local.json')
        self.load_selected_user()
        self.theme_cls.primary_palette = 'BlueGray'
        self.theme_cls.theme_style = 'Light'
        root = Builder.load_string(KV)
        Clock.schedule_once(lambda dt: self.refresh_all(), 0.5)
        # If on Android, ensure monthly alarm is scheduled
        Clock.schedule_once(lambda dt: self.ensure_monthly_alarm(), 1)
        return root

    def load_selected_user(self):
        self.selected_user = self.store.get('selected_user')['name'] if self.store.exists('selected_user') else None

    def save_selected_user(self, name):
        self.store.put('selected_user', name=name)
        self.selected_user = name

    def open_users_dialog(self):
        items = []
        self.users = self.db.list_users()
        for u in self.users:
            items.append(OneLineListItem(text=u, on_release=lambda x, u=u: self._select_user_from_dialog(u)))
        items.append(OneLineListItem(text='Add new user...', on_release=lambda x: self._show_add_user_dialog()))
        dlg = MDDialog(title='Select user', type='simple', items=items)
        dlg.open()

    def _select_user_from_dialog(self, username):
        self.save_selected_user(username)
        self.root.get_screen('dashboard').selected_user_display = f'User: {username}'
        self.refresh_all()

    def _show_add_user_dialog(self):
        self.new_user_field = MDTextField(hint_text='Name')
        dlg = MDDialog(title='Add user', type='custom', content_cls=self.new_user_field,
                       buttons=[MDTextField(text='CANCEL'),])
        # Simpler add dialog: just read textbox and use Add button
        dlg = MDDialog(title='Add user', type='custom', content_cls=self.new_user_field,
                       buttons=[MDTextField(text='')])
        # Use a simple approach:
        add_dlg = MDDialog(title='Add user', type='custom', content_cls=self.new_user_field,
                           buttons=[])
        add_dlg.open()

    def show_date_picker(self):
        date = MDDatePicker(year=datetime.date.today().year, month=datetime.date.today().month, day=datetime.date.today().day)
        date.bind(on_save=self.on_date_selected)
        date.open()

    def on_date_selected(self, instance, value, date_range):
        scr = self.root.get_screen('add')
        scr.chosen_date = str(value)
        try:
            scr.ids.date_label.text = str(value)
        except Exception:
            pass

    def save_entry(self, kind):
        scr = self.root.get_screen('add')
        amt_txt = scr.ids.amount.text.strip()
        if not amt_txt:
            self.show_toast('Enter amount')
            return
        try:
            amt = float(amt_txt)
        except:
            self.show_toast('Invalid amount')
            return
        cat = scr.ids.category.text.strip()
        note = scr.ids.note.text.strip()
        date_text = scr.chosen_date
        user = self.selected_user or 'Default'
        self.db.add_entry(user, kind, amt, cat, note, date_text)
        self.show_toast('Saved')
        scr.ids.amount.text = ''
        scr.ids.category.text = ''
        scr.ids.note.text = ''
        self.refresh_all()

    def show_toast(self, text):
        dlg = MDDialog(text=text, radius=[10, 10, 10, 10])
        dlg.open()
        Clock.schedule_once(lambda dt: dlg.dismiss(), 1.2)

    def refresh_all(self):
        self.users = self.db.list_users()
        dash = self.root.get_screen('dashboard')
        dash.greeting = 'Welcome!'
        dash.selected_user_display = f"User: {self.selected_user or '(choose user)'}"
        user = self.selected_user or 'Default'
        today = datetime.date.today()
        start_today = str(today)
        end_today = str(today)
        sums_today = self.db.sum_for_user_between(user, start_today, end_today)
        income_today = sums_today.get('income', 0)
        expense_today = sums_today.get('expense', 0)
        dash.today_summary = f'Income: {income_today}  Expense: {expense_today}  Net: {income_today - expense_today}'
        start_month = str(today.replace(day=1))
        sums_month = self.db.sum_for_user_between(user, start_month, str(today))
        income_month = sums_month.get('income', 0)
        expense_month = sums_month.get('expense', 0)
        dash.month_summary = f'Income: {income_month}  Expense: {expense_month}  Net: {income_month - expense_month}'
        hist = self.root.get_screen('history')
        hist.ids.history_list.clear_widgets()
        rows = self.db.get_entries_for_user(user)
        for r in rows:
            text = f"{r[6]} — {r[2].capitalize()} {r[3]} ({r[4]}) {r[5] or ''}"
            hist.ids.history_list.add_widget(OneLineListItem(text=text))

    def check_monthly_notification(self):
        last = self.db.meta_get('last_notified_month', '')
        now_month = datetime.date.today().strftime('%Y-%m')
        if last != now_month:
            user = self.selected_user or 'Default'
            today = datetime.date.today()
            start_month = str(today.replace(day=1))
            sums_month = self.db.sum_for_user_between(user, start_month, str(today))
            income_month = sums_month.get('income', 0)
            expense_month = sums_month.get('expense', 0)
            title = f'Monthly summary for {user}'
            msg = f'Income {income_month} — Expense {expense_month} — Net {income_month - expense_month}'
            try:
                notification.notify(title=title, message=msg, timeout=5)
            except Exception as e:
                print('notify error', e)
            self.db.meta_set('last_notified_month', now_month)

    def ensure_monthly_alarm(self):
        """On Android: schedule a monthly alarm that starts a python service.
           The service (service.py) will send the monthly notification.
        """
        if platform != 'android':
            return

        try:
            # use pyjnius to schedule an AlarmManager PendingIntent which starts the Python service
            from jnius import autoclass, cast

            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity

            Intent = autoclass('android.content.Intent')
            PendingIntent = autoclass('android.app.PendingIntent')
            Context = autoclass('android.content.Context')
            System = autoclass('java.lang.System')
            AlarmManager = autoclass('android.app.AlarmManager')
            Long = autoclass('java.lang.Long')

            # Intent to start the service; service will be in package <your.package>.service
            service_intent = Intent(activity.getApplicationContext(), autoclass(activity.getClass().getPackage().getName() + ".Service").__javaclass__)
            # The above reflection may not always work; a reliable approach is to use the full service class name.
            # Instead we'll create an intent that targets our python service by action string:
            service_action = 'org.test.familyexpense.MONTHLY_SERVICE'
            service_intent = Intent(service_action)
            service_intent.setPackage(activity.getPackageName())

            # Create a PendingIntent to start the service.
            pending = PendingIntent.getService(activity.getApplicationContext(), 0, service_intent, PendingIntent.FLAG_UPDATE_CURRENT)

            am = cast('android.app.AlarmManager', activity.getSystemService(Context.ALARM_SERVICE))

            # Schedule alarm for next 1st of month at 09:00 (local)
            now = java_time = System.currentTimeMillis()
            # Compute next month's first day time in millis (approx using Python)
            import calendar, time
            now_dt = datetime.datetime.now()
            year = now_dt.year
            month = now_dt.month
            # move to next month
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1
            target_dt = datetime.datetime(year, month, 1, 9, 0, 0)
            epoch_ms = int(time.mktime(target_dt.timetuple()) * 1000)

            # Use setInexactRepeating for monthly repeats (interval approximate)
            INTERVAL_DAY = 24 * 60 * 60 * 1000  # millis
            # approximate 30 days in millis
            INTERVAL_30_DAYS = 30 * INTERVAL_DAY

            am.setInexactRepeating(AlarmManager.RTC_WAKEUP, epoch_ms, INTERVAL_30_DAYS, pending)

            print('Monthly alarm scheduled (android).')
        except Exception as e:
            print('Error scheduling monthly alarm:', e)
            traceback.print_exc()


if __name__ == '__main__':
    # ensure DB file present in app directory
    if not os.path.exists(DB_FILE):
        ExpenseDB(DB_FILE)
    FamilyExpenseApp().run()

