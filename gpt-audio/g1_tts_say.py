#!/usr/bin/env python3
"""
Unitree G1 TTS / WAV playback helper.

예)
python3 g1_tts_say.py --interface eth0 --text "안녕하세요, G1입니다."
python3 g1_tts_say.py --interface eth0 --wav english.wav
"""

import argparse
import os
import sys
import time

SDK_PATH = "/home/unitree/unitree_sdk2_python"
EXAMPLE_AUDIO_PATH = os.path.join(SDK_PATH, "example", "g1", "audio")

for path in (SDK_PATH, EXAMPLE_AUDIO_PATH):
    if path not in sys.path:
        sys.path.insert(0, path)

from unitree_sdk2py.core.channel import ChannelFactoryInitialize  # type: ignore
from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient  # type: ignore
from wav import play_pcm_stream, read_wav  # type: ignore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="G1 스피커로 문장 또는 WAV 파일을 재생합니다"
    )
    parser.add_argument(
        "--interface",
        default="eth0",
        help="로봇과 연결된 네트워크 인터페이스 이름 (기본: eth0)",
    )
    parser.add_argument(
        "--text",
        help="로봇이 읽을 문장 (중국어 TTS)",
    )
    parser.add_argument(
        "--speaker-id",
        type=int,
        default=0,
        help="Unitree TTS 스피커 ID (기본 0)",
    )
    parser.add_argument(
        "--volume",
        type=int,
        default=None,
        help="0-100 범위 볼륨 (지정 시 즉시 설정)",
    )
    parser.add_argument(
        "--wav",
        help="16kHz 모노 WAV 파일 경로 (외부 영어 TTS 결과 등)",
    )
    parser.add_argument(
        "--app-name",
        default="aim_audio",
        help="PlayStream에 사용할 스트림 이름 (기본: aim_audio)",
    )
    parser.add_argument(
        "--chunk-bytes",
        type=int,
        default=96000,
        help="PlayStream 전송 시 청크 크기 (기본: 96000 bytes)",
    )
    parser.add_argument(
        "--chunk-sleep",
        type=float,
        default=0.6,
        help="각 청크 전송 간 대기 시간(초) (기본: 0.6)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    ChannelFactoryInitialize(0, args.interface)

    client = AudioClient()
    client.SetTimeout(10.0)
    client.Init()

    if args.volume is not None:
        client.SetVolume(max(0, min(100, args.volume)))
        time.sleep(0.2)  # 볼륨 적용 대기

    if (args.text is None) == (args.wav is None):
        print("❌ --text 또는 --wav 중 하나만 지정하세요.")
        return

    if args.text is not None:
        code = client.TtsMaker(args.text, args.speaker_id)
        if code == 0:
            print("✅ TTS 요청 전송 완료")
        else:
            print(f"❌ TTS 요청 실패 (코드: {code})")
        return

    if not os.path.isfile(args.wav):
        print(f"❌ WAV 파일을 찾을 수 없습니다: {args.wav}")
        return

    pcm_list, sample_rate, num_channels, is_ok = read_wav(args.wav)
    if not is_ok:
        print("❌ WAV 파일을 읽지 못했습니다. 16kHz 모노 16-bit PCM인지 확인하세요.")
        return

    if sample_rate != 16000 or num_channels != 1:
        print(
            f"❌ 지원하지 않는 WAV 형식입니다 (현재: {sample_rate}Hz, {num_channels}ch). 16kHz 모노만 지원됩니다."
        )
        return

    print(f"▶ WAV 전송 시작 ({len(pcm_list)} bytes)")
    play_pcm_stream(
        client,
        pcm_list,
        stream_name=args.app_name,
        chunk_size=args.chunk_bytes,
        sleep_time=args.chunk_sleep,
    )

    total_seconds = len(pcm_list) / (2 * sample_rate)
    time.sleep(max(0.0, total_seconds) + 0.3)

    client.PlayStop(args.app_name)
    print("✅ WAV 재생 완료")


if __name__ == "__main__":
    main()
