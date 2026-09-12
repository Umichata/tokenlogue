#!/usr/bin/env bash
set -Eeuo pipefail
umask 022
export LC_ALL=C TZ=UTC
export CC=clang CXX=clang++

work=$PWD
[[ $(id -u) != 0 ]] || { printf 'Compilation must use a non-root UID\n' >&2; exit 1; }
[[ $work == /build-one || $work == /build-two ]] || exit 1
: "${SOURCE_DATE_EPOCH:?}"
: "${RUNTIME_VERSION:?}"
prefix=$work/prefix
upstream=$work/sources/type2-runtime-caf24f9f712084686bfc24a70b75e50df0aefb9c
mkdir -p "$prefix" "$work/reports"

repro_flags="-march=x86-64 -mtune=generic -ffile-prefix-map=$work=/usr/src/runtime -fdebug-prefix-map=$work=/usr/src/runtime -fmacro-prefix-map=$work=/usr/src/runtime -ffile-prefix-map=/tmp=/usr/src/tmp"
export CFLAGS="-Os -ffunction-sections -fdata-sections -fPIC $repro_flags"
export CXXFLAGS="$CFLAGS"
export LDFLAGS='-Wl,--build-id=none'
export PKG_CONFIG_PATH="$prefix/lib/pkgconfig"
{
    printf 'SOURCE_DATE_EPOCH=%s\nLC_ALL=C\nTZ=UTC\numask=022\n' "$SOURCE_DATE_EPOCH"
    printf 'CFLAGS=%s\nLDFLAGS=%s\n' "$CFLAGS" "$LDFLAGS"
    printf 'uid=%s\n' "$(id -u)"
    printf 'gid=%s\n' "$(id -g)"
    uname -srm
    cat /etc/os-release
    clang --version
    gcc --version
    ld --version
    ar --version
    objcopy --version
    strip --version
    make --version
    meson --version
    ninja --version
    autoconf --version
    automake --version
    libtool --version
    pkg-config --version
    python3 --version
    apk --version
} > "$work/reports/toolchain.txt" 2>&1
cp /lib/apk/db/installed "$work/reports/installed"

cd "$work/sources/fuse-3.15.0"
patch --batch --fuzz=0 -p1 < "$upstream/patches/libfuse/mount.c.diff"
meson setup build --wrap-mode=nodownload --prefix="$prefix" --libdir=lib \
    --default-library=static -Dutils=false -Dexamples=false -Dtests=false \
    -Duseroot=false -Dinitscriptdir= -Dudevrulesdir="$prefix/udev"
meson compile -C build -j 2
meson install -C build --no-rebuild
cp build/meson-logs/meson-log.txt "$work/reports/libfuse-meson.log"

cd "$work/sources/squashfuse-0.5.2"
./autogen.sh
./configure --prefix="$prefix" --libdir="$prefix/lib" --disable-shared \
    --enable-static --with-zlib=/usr --with-zstd=/usr \
    --without-xz --without-lzo --without-lz4 LDFLAGS="-static -L$prefix/lib -Wl,--build-id=none"
make -j2
make install
install -m 644 ./*.h "$prefix/include/squashfuse/"
cp config.log "$work/reports/squashfuse-config.log"

cd "$upstream"
patch --batch --fuzz=0 -p1 < /recipe/patches/runtime-makefile.patch
cd src/runtime
printf '%s\n' "$RUNTIME_VERSION" > version
make runtime \
    CPPFLAGS="-I$prefix/include -I$prefix/include/squashfuse -I$prefix/include/fuse3" \
    REPRO_CFLAGS="$repro_flags -fPIE -save-temps=obj --rtlib=libgcc -fuse-ld=bfd -MD -MF $work/reports/runtime-headers.d" \
    LDFLAGS="-L$prefix/lib -Wl,--build-id=none,-Map,$work/reports/runtime.map,--trace"
cp runtime.i "$work/reports/runtime-preprocessed.c"

# Preserve the upstream ELF operations, in their original order.
objcopy --only-keep-debug runtime "$work/runtime-x86_64.debug"
strip --strip-debug --strip-unneeded runtime
cp runtime "$work/runtime-x86_64"
cd "$work"
objcopy --add-gnu-debuglink=runtime-x86_64.debug runtime-x86_64
printf 'AI\002' | dd of=runtime-x86_64 bs=1 count=3 seek=8 conv=notrunc
chmod 0755 runtime-x86_64
readelf -h -l -d -V -S -n -A -W runtime-x86_64 > reports/readelf.txt
file runtime-x86_64 > reports/file.txt
sha256sum runtime-x86_64 > reports/runtime.sha256
python3 /recipe/build_runtime.py inside-link "$work"
