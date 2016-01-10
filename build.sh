CWD=`pwd`

python parse_code_2015-06.py ./2015-06 > 2015-06.xml &&
echo 'inserting tables' &&
python insert_tables.py &&
echo 'python splitting' &&
python split_up.py ../dc-code-prototype < 2015-06t.xml &&
cd ../dc-code-prototype &&
git checkout Title-1/Chapter-15/ &&
echo 'generating html' &&
cd ../simple-generator &&
echo 'making index' &&
node make_index.js ../dc-code-prototype &&
echo 'building html' &&
node index.js ../dc-code-prototype/ simple

cd $CWD
tput bel