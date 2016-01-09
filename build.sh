CWD=`pwd`

python parse_code_2015-06.py ./2015-06 > 2015-06.xml &&
echo 'inserting tables' &&
python insert_tables.py &&
echo 'python splitting' &&
python split_up.py ../dc-code-prototype < 2015-06t.xml &&
echo 'generating html' &&
cd ../simple-generator &&
python prebuild.py &&
cd ./simple &&
git checkout Title-1/Chapter-15/ &&
git checkout sections/1-15-*

cd $CWD
tput bel