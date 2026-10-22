#!/usr/bin/env bash
# Shrink a Raspberry Pi SD-card image so it fits a smaller card. The original is never modified.
#
#   sudo bash tools/shrink-image.sh <image.img> [size]       size default 24G (fits any 32 GB card)
#   (Windows: wsl -d Ubuntu -u root bash /mnt/c/.../tools/shrink-image.sh /mnt/c/.../image.img 24G)
#
# Writes <image>-<size>.img next to the input: the same card, with the root (ext4) partition
# cut down to <size> minus the boot partition. Uses e2fsck, resize2fs, sfdisk, losetup.
set -euo pipefail

IMG="${1:?usage: shrink-image.sh <image.img> [size, e.g. 24G]}"
SIZE="${2:-24G}"
OUT="${IMG%.img}-${SIZE}.img"
WORKDIR="${SHRINK_WORKDIR:-/var/tmp}"  # fast native Linux disk (not /mnt/c) for the in-place work
WORK="$WORKDIR/shrink-$$.img"
LOOP=""

[ "$(id -u)" -eq 0 ] || { echo "Run as root (sudo, or wsl -u root)"; exit 1; }
for t in e2fsck resize2fs sfdisk losetup numfmt; do command -v $t >/dev/null || { echo "missing $t"; exit 1; }; done
[ -f "$IMG" ] || { echo "No such image: $IMG"; exit 1; }

cleanup() { [ -n "$LOOP" ] && losetup -d "$LOOP" 2>/dev/null; rm -f "$WORK"; }
trap cleanup EXIT

TARGET=$(numfmt --from=iec "$SIZE")
echo "== Copying image to $WORK (the original stays untouched)"
cp --sparse=always "$IMG" "$WORK"

# Partition 2 = root filesystem (Raspberry Pi OS layout: p1 FAT boot, p2 ext4 root)
read -r P2_START P2_SECTORS < <(sfdisk -d "$WORK" | awk -F'[=,]' '/(img|-)2 :/{gsub(/ /,""); print $2, $4}')
[ -n "${P2_START:-}" ] || { echo "Couldn't find partition 2 in $IMG"; exit 1; }
NEW_SECTORS=$(( TARGET / 512 - P2_START ))
echo "   root partition: starts at sector $P2_START, $((P2_SECTORS * 512 / 1024**3)) GiB now -> $((NEW_SECTORS * 512 / 1024**3)) GiB"
[ "$NEW_SECTORS" -lt "$P2_SECTORS" ] || { echo "Image already fits in $SIZE; nothing to do."; exit 0; }

LOOP=$(losetup -f --show -o $(( P2_START * 512 )) --sizelimit $(( P2_SECTORS * 512 )) "$WORK")
echo "== Checking the filesystem"
e2fsck -f -y "$LOOP" || [ $? -le 1 ]
USED_K=$(( $(dumpe2fs -h "$LOOP" 2>/dev/null | awk -F: '/^Block count/{bc=$2} /^Free blocks/{fb=$2} /^Block size/{bs=$2} END{print (bc-fb)*bs}') / 1024 ))
FS_K=$(( NEW_SECTORS * 512 / 1024 - 4096 ))  # leave a little slack inside the partition
echo "   in use: $((USED_K / 1024**2)) GiB; new filesystem size: $((FS_K / 1024**2)) GiB"
MARGIN_K="${SHRINK_MARGIN_K:-$(( 1024**2 ))}"  # keep at least 1 GiB free after shrinking
[ "$FS_K" -gt $(( USED_K + MARGIN_K )) ] || { echo "Too small: the data plus 1 GiB spare needs more than $SIZE"; exit 1; }

echo "== Shrinking the filesystem (moves data down if needed; takes a few minutes)"
resize2fs -p "$LOOP" "${FS_K}K"
losetup -d "$LOOP"; LOOP=""

echo "== Shrinking partition 2 and trimming the file"
echo ",$NEW_SECTORS" | sfdisk --no-reread --no-tell-kernel -q -N 2 "$WORK"
truncate -s $(( (P2_START + NEW_SECTORS) * 512 )) "$WORK"

LOOP=$(losetup -f --show -o $(( P2_START * 512 )) --sizelimit $(( NEW_SECTORS * 512 )) "$WORK")
e2fsck -f -n "$LOOP" >/dev/null && echo "   filesystem check after shrink: clean"
losetup -d "$LOOP"; LOOP=""

echo "== Writing $OUT"
cp --sparse=always "$WORK" "$OUT"
echo "Done: $OUT ($(numfmt --to=iec "$(stat -c %s "$OUT")")) - write it with Win32 Disk Imager."
