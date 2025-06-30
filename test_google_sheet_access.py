import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Your service account JSON dict (with properly formatted private_key)
SERVICE_ACCOUNT_JSON = {
  "type": "service_account",
  "project_id": "joes-mobile-shop",
  "private_key_id": "14997c0c55aeb2a4fa3e88df83af70be43d672e0",
  "private_key": """-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC1We6v3cds4mGO
ZkV7SxKpt1BT6sWAE61nBgjW7PvEnfJeLkXPbUiEthqz4947DnkN002fvYxFdL6B
/wULgUenMXqdmOLiFWTc0K3oE1ZI2B313HAMTsarVHOa+zGoNxuONtXCLbbs/sN4
/14vpnqrtErsdZcbJEtLi039FxIPe2o3Xx2oyDVAV1KNQc+Ns3efjq5zmN2NmWWa
flXTKecUqVlXi2kGmO9t3eViCFf9bDYl3U9/bv0M/leZdT+bH1XMQyK131qSCdTA
nBVl8CsybvVlVkGwdbgAYK44x2CCgLqHBzbXl7Wa5pRYba+rV6VGUKa23zLOEl5r
qCr7bJddAgMBAAECggEAT1nees1L6XTUwv41ANHEhMZVO6LKcFQr15xoWcKwF0QV
POh6W1yyEn+sB3J5VtXqWgZPPMovimSexzrS9knHFH0t7a9r9wjtbUFSFu3/HziR
Q3cFAB2oCGeXfgTToYsbX4rW1XQzSlffKB51E9yAaIknD3gUeifTWmbF5SwnFuZo
kydRLQC+8zVdp5JImbZj0Hp7iM+/JN0VVdIT5FWL0FJzMzurhVMrCgKd8kftjaqV
QbMkY2NGSskw4zX04GTi1Za3vHWQq1eAYfZ2hRDa1Fu8gmzKjpODPj5WEAEW5VbN
ptfOIrdM9KfBij5gcPkV6mws8S1KsZ+2yLk78qFPcQKBgQDlRAKz8cHcsIbdNTwd
Uys1q3uPGQcE41B2xdbMayIXK4n3zvxEbl1x/BiseyLbRQQ8vKvs/uoll2hbCQrn
5LAQA1GO/4HEws1EeON9TjRZPi3L8+hAo339Rag9aMqhsui8yjUWcAbJXYfBmRDk
8fw2HVetECrmdnqgsoVj8r7ouwKBgQDKf5em2K53PImRVOFg2OBWvw/EBARLiVvf
/ELkg9XRW6hm3/MtA187VgJtrBoo7pyVbB4VRqMbrnCQ7sULIYLZIpiKuJFjqmIP
kh0lry6yqXTTVCLvM59VKAxa1JDOUqG2jeLCJStwnVCghbp4GTkXf4Nj39G5TQl4
upmKZpUqxwKBgHOeGqbYcmVy+HAx2oEHYjEMq6D8hBeo8vkSyEIKfQSmRkucLIfu
CF3lPiQtbOSbJ4nhs+oum7IdatkN9FwBbfCFW+n7XFv3yUCQnligybF/s+S4uhVu
3aiOKkvdvuJQsSIT7zXDhQijjETLhkOO7Rv1LDPwhVH3yduka7R9xFzlAoGBAJiM
VFeJ5qzGuy/zzLGj0CUpXBwjloS9Hqx3IoF526sTLKMLVOt1HdnaaovqWe66CtX6
FBOdGiUxXXWhmmlPPn6LNHVUo5p8cdEfFrwb48cOJ4dIW+Ttc7u4Js6KUehMkayv
6MKvM7FroaC7/YSaI8tS8U1dAGZi5Z7AnAiKTRdjAoGBAK3i9O74I3y71qZIA4rH
8uKvvtfK/GXqBBLDhMFSXclzpdBapCHE2ZibPotv5mc6/Gz92CCdvbl3K32mPrDs
fNIop41nhx6w2z21mAbmbz4EAQjRhFkVmjjRSOI4SdklOs9bWwdezDVLGzkrffQx
JoMufYu58roQoV09Wxu1FD7C
-----END PRIVATE KEY-----""",
  "client_email": "google-sheets-access@joes-mobile-shop.iam.gserviceaccount.com",
  "client_id": "106671334937759897658",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/google-sheets-access@joes-mobile-shop.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
}

# Your Google Sheet ID
GOOGLE_SHEET_ID = "1IGwC6Ztxcc0BJ1a0qPkXnTQjccSFNqOIaTu1IgwAt6M"

def main():
    try:
        # Create credentials object from service account info
        credentials = service_account.Credentials.from_service_account_info(
            SERVICE_ACCOUNT_JSON,
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )

        # Build the Sheets API client
        service = build('sheets', 'v4', credentials=credentials)

        # Call the Sheets API to get data from the first sheet (Sheet1!A1:D5 for example)
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=GOOGLE_SHEET_ID, range="Sheet1!A1:D5").execute()

        values = result.get('values', [])

        if not values:
            print("No data found in the sheet.")
        else:
            print("Data from sheet:")
            for row in values:
                print(row)

        print("\n✅ Service account credentials are valid and access successful.")

    except Exception as e:
        print(f"❌ Invalid or expired service account credentials.\nError: {e}")

if __name__ == "__main__":
    main()
