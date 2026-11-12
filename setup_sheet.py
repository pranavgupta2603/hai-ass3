"""Initialize the new Ass3 events worksheet; never clears existing data."""
import argparse
import tomllib
import gspread
from google.oauth2.service_account import Credentials
from storage import HEADERS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--secrets', default='.streamlit/secrets.toml')
    args = parser.parse_args()
    with open(args.secrets, 'rb') as f:
        cfg = tomllib.load(f)['google_sheets']
    creds = Credentials.from_service_account_info(cfg['service_account'],
             scopes=['https://www.googleapis.com/auth/spreadsheets'])
    book = gspread.authorize(creds).open_by_key(cfg['spreadsheet_id'])
    try:
        sheet = book.worksheet(cfg.get('worksheet', 'events'))
    except gspread.WorksheetNotFound:
        sheet = book.add_worksheet(cfg.get('worksheet', 'events'), rows=1000, cols=len(HEADERS))
    values = sheet.get_all_values()
    if not any(any(row) for row in values):
        sheet.append_row(HEADERS, value_input_option='RAW')
        sheet.freeze(rows=1)
    elif values[0] != HEADERS:
        raise ValueError('Existing worksheet is not an Ass3 events sheet; nothing was changed.')
    print('Ass3 worksheet is ready. Existing records were preserved.')


if __name__ == '__main__':
    main()
