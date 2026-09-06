app running local on macosx, connected directly to a Brother QL700 thermal printer.
lightweight, fast, easy to deploy, using best technology for connecting to printer and hosting locally, nodejs or python perhaps?

purpose of the app, web app, iphone
present a front end that collects personal contact data and makes a digital vcf contact card in the form of a qrcode

the qrcode is sent to the printer
information is recorded to a local sqllite database

1. meet code splash
2. agree to GDPR and processing of storage of personal information
- if agree, data is processed and stored
- if not agree, data is processed but not stored
3. screen with data collection points
- name
- company
- position
- email
- phone
- url
4. generate 
- qr code is shown
- save QR code, save to downloads
- print QR code, prints to the Brother QL700 without any dialogue, it just prints, with name and QR code
5. done
- back to the start



git init
git add README.md
git commit -m "first commit"
git branch -M main
git remote add origin git@github.com:oribotic/mcode.git
git push -u origin main

git config --global user.email "matthew.gardiner@ars.electronica.art"
git config --global user.name "Matthew Gardiner"