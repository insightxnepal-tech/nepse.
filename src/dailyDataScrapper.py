# import required library and required constants
import time
import requests
import pandas as pd
from io import StringIO
from pathlib import Path
from bs4 import BeautifulSoup
from utils.status import getStatus
from constants.url import dailyPriceUrl

html = requests.get(dailyPriceUrl).text
bs = BeautifulSoup(html, "lxml")

# today date in yyyy-mm-dd format
today = bs.find("span", {"class": "text-org"}).text

# get html tables
tables = pd.read_html(StringIO(html))

# select the first table i.e. the stock price table
dataTable = tables[0]

fileDir = Path("../data/company-wise/")
for file in fileDir.glob("*.csv"):
    # first check if data already exist for this date
    existingDf = pd.read_csv(file)
    lastRow = existingDf.iloc[-1]
    lastDate = lastRow["published_date"]
    if str(lastDate) != str(today):
        symbol = str(file).split(".")[2].split("/")[-1]
        data = dataTable.loc[dataTable["Symbol"] == symbol]
        if len(data) == 1:
            row = data.iloc[0]
            status = getStatus(float(row["Open"]), float(row["Close"]))
            dataRow = [
                [
                    today,
                    float(row["Open"]),
                    float(row["High"]),
                    float(row["Low"]),
                    float(row["Close"]),
                    float(row["Diff %"]),
                    float(row["Vol"]),
                    float(row["Turnover"]),
                    status,
                ]
            ]
            dataframe = pd.DataFrame(dataRow)
            dataframe.to_csv(file, mode="a", header=False, index=False)
