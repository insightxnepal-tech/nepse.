# import required lib and configs
import requests
import pandas as pd
from pathlib import Path
from config.cookies import cookies
from config.headers import headers
from constants.url import historyUrl
from constants.companyIdMap import companyIdMap
from utils.params import getParams
from utils.flatten import flatten


def getData(company):
    # get company symbol
    companySymbol = companyIdMap[company]

    # data collection start from here
    print(f"Collecting data of {company}...")
    print(".........")

    # set params for API, (set size = 1, for start to get the total size of data)
    params = getParams(1, 1, companySymbol)

    # request API to get data with robust POST handling and proper Referer
    request_headers = dict(headers)
    # set Referer to the specific company page
    request_headers['Referer'] = f"https://www.sharesansar.com/company/{company.lower()}"
    # include XSRF token if present
    xsrf_token = cookies.get('XSRF-TOKEN')
    if xsrf_token:
        request_headers['X-XSRF-TOKEN'] = xsrf_token
    # try JSON payload POST first
    response = requests.post(historyUrl, headers=request_headers, json=params, cookies=cookies)
    if not response.ok:
        # fallback to form-encoded POST
        response = requests.post(historyUrl, headers=request_headers, data=params, cookies=cookies)
    if not response.ok:
        raise RuntimeError(f"Failed to fetch data for {company}: {response.status_code}")
    json_data = response.json()
    # get total number of data available, fallback to length of data list if key missing
    totalRecords = json_data.get('recordsTotal')
    if totalRecords is None:
        totalRecords = len(json_data.get('data', []))
    # set the start to 1 and total size of data to 50

    # set the start to 1 and total size of data to 50
    start = 1
    size = 50

    # totalLoop = total number of iteration we have to do to get full data;
    totalLoop = (totalRecords // 50) + 1

    # intialized an empty array to store data that we got in the loop
    data = []

    # loop
    for i in range(1, totalLoop):
        dataParams = getParams(start, size, companySymbol)
        response = requests.get(historyUrl, headers=request_headers, params=dataParams, cookies=cookies)
        data.append(response.json()["data"])
        start = start + 50

    # flat the 2d data to 1d array
    dataArray = flatten(data)

    # convert to dataframe and save to csv in reverse order
    df = pd.DataFrame.from_dict(dataArray)[::-1]

    # remove unwanted column DT_Row_Index
    df = df.drop(columns="DT_Row_Index")

    # save to file
    fileName = f"../data/company-wise/{company}.csv"
    filepath = Path(fileName)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(filepath, index=False)

    # print after the data collection is completed
    print(".........")
    print(f"Collection completed of {company}...")


for company in companyIdMap:
    try:
        getData(company)
    except Exception as e:
        print(f"Error fetching data for {company}: {e}")
        continue
