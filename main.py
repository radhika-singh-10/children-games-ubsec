from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import FileResponse,JSONResponse
import os
import random
import uvicorn
from typing import List
import csv
import httpx
import pandas as pd
import logging
import requests
from io import StringIO
import httpx
import json
import asyncio
import configparser
from pydub import AudioSegment
from tempfile import NamedTemporaryFile

app = FastAPI()
#tzoJVSdeeEOPopTNX3T3dbCIv0m+FU6JpYDnh6pp/AXV0/ho
#7005400361

@app.post("/upload_audio/")
async def upload_audios(
    api_key: str = Form(...),user_id: str = Form(...),
    display_name: str = Form(...),description: str = Form(...),
    files: List[UploadFile] = File(...)
):
    try:
        for file in files:
            if file.content_type != "audio/mpeg":
                raise HTTPException(status_code=400, detail=f"Invalid file type for {file.filename}. Only mp3 files are accepted.")
        
        async def upload_and_check(file: UploadFile):
            file_content = await file.read()

            payload = {
                "assetType": "Audio",
                "displayName": display_name,
                "description": description,
                "creationContext": {
                    "creator": {
                        "userId": user_id
                    }
                }
            }

            files = {
                'request': (None, json.dumps(payload), 'application/json'),
                'fileContent': (file.filename, file_content, 'audio/mpeg')
            }
            #timeout = httpx.Timeout(None)#httpx.Timeout(10.0, read=372000000000000.0) 
            async with httpx.AsyncClient(timeout=None) as client:
                try:
                    upload_response = await client.post(
                        'https://apis.roblox.com/assets/v1/assets',
                        headers={'x-api-key': api_key},
                        files=files
                    )
                except httpx.RequestError as exc:
                    print(f"Exception : {exc}")
                    raise HTTPException(status_code=500, detail=f"An error occurred while requesting {exc.request.url}.") from exc
                except httpx.TimeoutException:
                    raise HTTPException(status_code=504, detail="The request timed out.")
            if upload_response.status_code != 200:
                raise HTTPException(status_code=upload_response.status_code, detail=upload_response.text)
            
            upload_data = upload_response.json()
            operation_id = upload_data.get('operationId')
            print(upload_response)
            if not operation_id:
                raise HTTPException(status_code=500, detail="Operation ID not found in the upload response.")

            async def check_moderation_status():
                async with httpx.AsyncClient() as client:
                    while True:
                        moderation_response = await client.get(
                            f'https://apis.roblox.com/assets/v1/operations/{operation_id}',
                            headers={'x-api-key': api_key}
                        )
                        if moderation_response.status_code != 200:
                            print(moderation_response)
                            continue
                            #raise HTTPException(status_code=moderation_response.status_code, detail=moderation_response.text)
                        
                        moderation_data = moderation_response.json()
                        status = moderation_data.get('done')
                        print(moderation_data)
                        if status:
                            return moderation_data
                        await asyncio.sleep(60)

            moderation_result = await check_moderation_status()
            print(moderation_result)
            return {
                "fileName": file.filename,
                "operationId": operation_id,
                "asset_id":moderation_result.get('response', {}).get('path').split("/")[1],
                "moderationResult": moderation_result.get('response', {}).get('moderationResult', {}).get('moderationState')
            }
            
        
        results = await asyncio.gather(*[upload_and_check(file) for file in files])
        df_new = pd.DataFrame(results)
        csv_path = "./moderation_results.csv"
        
        if os.path.exists(csv_path):
            df_existing = pd.read_csv(csv_path)
            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
        else:
            df_combined = df_new
        
        df_combined.to_csv(csv_path, index=False)
        return FileResponse(csv_path, media_type='text/csv', filename='moderation_results.csv')
    except Exception as ex:
        print(ex)
        logging.warning(ex)





@app.post("/get_updated_status")
async def update_moderation_results(api_key: str = Form(...)):
    updated_rows = []
    try:
        with open('./moderation_results_copy.csv', mode='r') as file:
            csv_reader = csv.DictReader(file)
            rows = list(csv_reader)
            print(rows)
        for row in rows:
            operation_id = row['operationId']
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(f'https://apis.roblox.com/assets/v1/operations/{operation_id}',
                                                headers={'x-api-key': api_key})

                    if response.status_code == 401:
                        print("Unauthorized access, stopping the update process.")
                        return {"message": "Unauthorized access, CSV not modified."}

                    response.raise_for_status()
                    moderation_data = response.json()
                    
                row['moderationResult'] = moderation_data.get('response', {}).get('moderationResult', {}).get('moderationState')
                updated_rows.append(row)
            except httpx.HTTPError as http_err:
                print(f"Error fetching data for operationId {operation_id}: {str(http_err)}")
                continue

        with open('./moderation_results_copy.csv', mode='w', newline='') as file:
            fieldnames = updated_rows[0].keys()
            csv_writer = csv.DictWriter(file, fieldnames=fieldnames)
            csv_writer.writeheader()
            csv_writer.writerows(updated_rows)
              
        return {"message": "Moderation results updated successfully."}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))



@app.get("/")
async def read_root():
    return {"message": "Roblox Audio testing API!"}



if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5001)



