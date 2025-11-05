#!/usr/bin/env python3
"""
Prompt Templates for GPT Vision Analysis
Customize these for different robotics tasks
"""

# ============================================================
# Scene Understanding Prompts
# ============================================================

SCENE_UNDERSTANDING = """Analyze this scene from a robot's perspective. Describe:
1. What objects are visible
2. The spatial layout (left, right, center, near, far)
3. Any obstacles or hazards
4. Suggested actions for navigation

Depth at center: {depth_m}m
Be concise and actionable."""

OBJECT_DETECTION = """What objects do you see in this image?
List them with their approximate locations (left/center/right, near/far).

Depth at center: {depth_m}m
Format: object_name (location, distance)"""

OBSTACLE_DETECTION = """Identify any obstacles or hazards in this scene that a mobile robot should avoid.
Consider:
- Physical obstacles (walls, furniture, objects)
- Potential hazards (stairs, uneven surfaces, fragile items)
- Clearance for navigation

Depth at center: {depth_m}m
Prioritize by severity."""

# ============================================================
# Task-Specific Prompts
# ============================================================

PERSON_TRACKING = """Is there a person visible in this image?
If yes:
- Approximate position (left/center/right)
- Distance (use depth: {depth_m}m as reference)
- Activity or pose if identifiable

If no person: state "No person detected"."""

ROOM_CLASSIFICATION = """What type of room or environment is this?
Options: kitchen, living room, bedroom, office, hallway, outdoor, unknown

Provide your answer and 2-3 key identifying features.

Depth at center: {depth_m}m"""

SAFETY_CHECK = """From a robot safety perspective, is it safe to move forward in this scene?

Consider:
- Obstacles in path
- Clearance height and width
- Surface stability
- Proximity to humans or fragile objects

Depth reading: {depth_m}m
Answer: SAFE, CAUTION, or STOP, with brief reason."""

# ============================================================
# Navigation Prompts
# ============================================================

DIRECTION_RECOMMENDATION = """Based on this view, which direction should the robot move?

Options:
- FORWARD: clear path ahead
- LEFT: obstacle on right, clear on left
- RIGHT: obstacle on left, clear on right
- STOP: blocked or unsafe
- BACKWARD: need to retreat

Depth at center: {depth_m}m
Provide direction and brief reasoning."""

PATH_DESCRIPTION = """Describe the navigable paths in this scene.
Focus on:
- Clear areas for movement
- Width of passages
- Any turns or corridors
- Surface type (if identifiable)

Depth at center: {depth_m}m"""

# ============================================================
# Korean Version Prompts (한국어 버전)
# ============================================================

SCENE_UNDERSTANDING_KR = """로봇 관점에서 이 장면을 분석하세요. 다음을 설명하세요:
1. 보이는 물체들
2. 공간 배치 (왼쪽, 오른쪽, 중앙, 가까이, 멀리)
3. 장애물이나 위험 요소
4. 주행을 위한 제안 행동

중앙 거리: {depth_m}m
간결하고 실행 가능하게 작성하세요.

물체 표기 양식: - 물체명 (위치, 약 거리m)
예: - 의자 (왼쪽 뒤쪽, 약 1.5m)"""

OBJECT_DETECTION_KR = """이 이미지에서 어떤 물체들이 보이나요?
대략적인 위치와 함께 나열하세요 (왼쪽/중앙/오른쪽, 가까이/멀리).

중앙 거리: {depth_m}m
형식: 물체명 (위치, 거리)"""

OBSTACLE_DETECTION_KR = """이동 로봇이 피해야 할 장애물이나 위험 요소를 식별하세요.
고려 사항:
- 물리적 장애물 (벽, 가구, 물체)
- 잠재적 위험 (계단, 고르지 않은 표면, 깨지기 쉬운 물건)
- 주행 여유 공간

중앙 거리: {depth_m}m
심각도 순으로 우선순위를 매기세요."""

PERSON_TRACKING_KR = """이 이미지에 사람이 보이나요?
보인다면:
- 대략적인 위치 (왼쪽/중앙/오른쪽)
- 거리 (기준: {depth_m}m)
- 식별 가능한 활동이나 자세

사람이 없으면: "사람 감지 안 됨"이라고 답하세요."""

ROOM_CLASSIFICATION_KR = """이곳은 어떤 종류의 방이나 환경인가요?
선택지: 주방, 거실, 침실, 사무실, 복도, 실외, 알 수 없음

답변과 함께 2-3가지 주요 식별 특징을 제시하세요.

중앙 거리: {depth_m}m"""

SAFETY_CHECK_KR = """로봇 안전 관점에서 이 장면에서 전진하는 것이 안전한가요?

고려 사항:
- 경로상의 장애물
- 높이 및 폭 여유 공간
- 표면 안정성
- 사람이나 깨지기 쉬운 물체와의 근접성

거리 측정값: {depth_m}m
답변: SAFE, CAUTION, 또는 STOP, 간단한 이유 포함."""

DIRECTION_RECOMMENDATION_KR = """이 화면을 기반으로 로봇이 어느 방향으로 이동해야 하나요?

선택지:
- FORWARD: 앞쪽 경로 확보
- LEFT: 오른쪽에 장애물, 왼쪽 확보
- RIGHT: 왼쪽에 장애물, 오른쪽 확보
- STOP: 막힘 또는 불안전
- BACKWARD: 후진 필요

중앙 거리: {depth_m}m
방향과 간단한 이유를 제시하세요."""

PATH_DESCRIPTION_KR = """이 장면에서 주행 가능한 경로를 설명하세요.
집중할 사항:
- 이동 가능한 공간
- 통로의 폭
- 회전이나 복도
- 표면 유형 (식별 가능한 경우)

중앙 거리: {depth_m}m"""

# ============================================================
# Custom Prompt Builder
# ============================================================

def build_prompt(template, depth_m=None, include_depth_image=False, **kwargs):
    """
    Build a prompt from a template with depth and custom parameters

    Args:
        template: Prompt template string
        depth_m: Depth measurement in meters
        include_depth_image: Whether depth image is included
        **kwargs: Additional formatting parameters

    Returns:
        Formatted prompt string
    """
    depth_str = f"{depth_m:.2f}" if depth_m is not None else "N/A"

    # Add depth image explanation if included
    depth_image_note = ""
    if include_depth_image:
        depth_image_note = f"\n\n[참고: 두 번째 이미지는 깊이 맵입니다. 파란색=가까움(0.5-1m), 초록색=중간(1-2m), 노란색/빨간색=멀리(2m+). 중앙 실측값: {depth_str}m. 각 물체는 위치와 거리만 간단히 표시하세요. 깊이맵 색상 언급 불필요. 예: 의자 (중앙-오른쪽, 약 1.5m)]"

    prompt = template.format(depth_m=depth_str, **kwargs)
    return prompt + depth_image_note


# ============================================================
# Example Usage
# ============================================================

if __name__ == "__main__":
    # Test prompt building
    depth = 1.25

    print("Scene Understanding Prompt:")
    print("=" * 60)
    print(build_prompt(SCENE_UNDERSTANDING, depth_m=depth))
    print()

    print("Safety Check Prompt:")
    print("=" * 60)
    print(build_prompt(SAFETY_CHECK, depth_m=depth))
