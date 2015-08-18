WORKINGDIR=`mktemp -d`
trap "rm -rf $WORKINGDIR" EXIT

cp "$1" "$WORKINGDIR/PKGBUILD"
cat > $WORKINGDIR/reader.sh << EOF
source PKGBUILD

function print_array () {
    local array=("\${@}")
    for elem in "\${array[@]}"
    do
      echo \${elem}
    done
}

echo [pkgname]
print_array \${pkgname[@]}
echo

echo \\<epoch\\>
echo \${epoch}
echo

echo \\<pkgver\\>
echo \${pkgver}
echo 

echo \\<pkgrel\\>
echo \${pkgrel}
echo

echo [source]
print_array \${source[@]}
EOF

(
  cd $WORKINGDIR
  env -i PATH="" /bin/bash --norc --noprofile -r "reader.sh"
) 2>/dev/null
