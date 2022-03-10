for d in */ ; do
  [ -L "${d%/}" ] && continue
  # echo "$d"
  cd $d
  sh build.sh
	cd ..
done