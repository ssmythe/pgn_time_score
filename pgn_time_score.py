#!/usr/bin/env python3
import argparse
import math
import re
import chess.pgn


def format_mmss(seconds):
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"


def parse_time_str(time_str):
    """
    Convert a clock string (e.g. "0:29:59.9") into seconds (float).
    Supports formats like H:MM:SS.s or MM:SS.s.
    """
    parts = time_str.split(":")
    if len(parts) == 3:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        return hours * 3600 + minutes * 60 + seconds
    elif len(parts) == 2:
        minutes = int(parts[0])
        seconds = float(parts[1])
        return minutes * 60 + seconds
    else:
        return float(time_str)


def process_game(game):
    """
    Process the chess.pgn.Game object to compute move times.
    Returns:
      - output_lines: list of formatted move lines (combined white/black per move number)
      - moves_info: list of individual move dicts (each with side, move, time_used)
      - initial_time: starting clock time (in seconds) per side.
    """
    try:
        initial_time = float(game.headers.get("TimeControl", "1800"))
    except ValueError:
        initial_time = 1800.0

    clock_pattern = re.compile(r"\[%clk\s+(\S+)\]")
    board = game.board()
    moves_info = []
    white_prev = initial_time
    black_prev = initial_time

    node = game
    while node.variations:
        next_node = node.variation(0)
        comment = next_node.comment
        match = clock_pattern.search(comment)
        if match:
            clock_time_str = match.group(1)
            clock_seconds = parse_time_str(clock_time_str)
        else:
            clock_seconds = None

        side = "W" if board.turn == chess.WHITE else "B"
        san_move = board.san(next_node.move)

        if clock_seconds is not None:
            if side == "W":
                time_used = white_prev - clock_seconds
                white_prev = clock_seconds
            else:
                time_used = black_prev - clock_seconds
                black_prev = clock_seconds
        else:
            time_used = 0.0

        moves_info.append({"side": side, "move": san_move, "time_used": time_used})

        board.push(next_node.move)
        node = next_node

    # Build a combined move list with move numbers.
    output_lines = []
    move_number = 1
    i = 0
    while i < len(moves_info):
        white_move = None
        black_move = None
        if i < len(moves_info) and moves_info[i]["side"] == "W":
            white_move = moves_info[i]
            i += 1
        if i < len(moves_info) and moves_info[i]["side"] == "B":
            black_move = moves_info[i]
            i += 1
        line = f"{move_number}. "
        if white_move:
            line += f"{white_move['move']} ({white_move['time_used']:.1f}s) "
        if black_move:
            line += f"{black_move['move']} ({black_move['time_used']:.1f}s)"
        output_lines.append(line.strip())
        move_number += 1

    return output_lines, moves_info, initial_time


def compute_stats(moves, initial_time):
    """
    Compute overall statistics for a list of moves.
    Returns a dict containing:
      - count: number of moves,
      - total_time: total time used,
      - avg_time: average move time,
      - std_dev: standard deviation,
      - consistency: (std_dev/avg_time)*100,
      - recommended_avg: ideal average move time based on 40 moves per side,
      - efficiency_ratio: (actual avg / recommended_avg)*100.

    For a G/30 game (1800 seconds) and 40 moves, the recommended average move time is 45.0 seconds.
    """
    if not moves:
        return {
            "count": 0,
            "total_time": 0.0,
            "avg_time": 0.0,
            "std_dev": 0.0,
            "consistency": 0.0,
            "recommended_avg": 0.0,
            "efficiency_ratio": 0.0,
        }
    count = len(moves)
    total_time = sum(m["time_used"] for m in moves)
    avg_time = total_time / count
    variance = sum((m["time_used"] - avg_time) ** 2 for m in moves) / count
    std_dev = math.sqrt(variance)
    consistency = (std_dev / avg_time * 100) if avg_time != 0 else 0.0

    # Use 40 moves per side as the basis for the recommended average.
    recommended_avg = initial_time / 40.0
    efficiency_ratio = (
        (avg_time / recommended_avg * 100) if recommended_avg != 0 else 0.0
    )

    return {
        "count": count,
        "total_time": total_time,
        "avg_time": avg_time,
        "std_dev": std_dev,
        "consistency": consistency,
        "recommended_avg": recommended_avg,
        "efficiency_ratio": efficiency_ratio,
    }


def analyze_segments(moves, recommended_avg=45.0):
    """
    Split moves into two segments and produce separate comments for the early and later game.
    Returns a tuple (early_comment, later_comment).
    """
    if len(moves) < 2:
        return (
            "Insufficient data for early game analysis.",
            "Insufficient data for later game analysis.",
        )
    half = len(moves) // 2
    first_half = moves[:half]
    second_half = moves[half:]
    avg_first = sum(m["time_used"] for m in first_half) / len(first_half)
    avg_second = sum(m["time_used"] for m in second_half) / len(second_half)

    # Early game analysis based on recommended average.
    early_comment = f"Early game average: {avg_first:.1f} s/move."
    if avg_first < recommended_avg * 0.9:
        early_comment += " Moves were notably faster than recommended."
    elif avg_first > recommended_avg * 1.1:
        early_comment += " Moves were notably slower than recommended."
    else:
        early_comment += " Early game move times were near optimal."

    # Later game analysis based on comparison to early game.
    later_comment = f"Later game average: {avg_second:.1f} s/move."
    if avg_second < avg_first * 0.9:
        later_comment += " Moves became significantly faster in the later game."
    elif avg_second > avg_first * 1.1:
        later_comment += " Moves became significantly slower in the later game."
    else:
        later_comment += (
            " Later game move times remained consistent with the early game."
        )

    return early_comment, later_comment


def efficiency_comment(eff_ratio):
    """
    Return a comment based on the overall clock efficiency.
    """
    if eff_ratio < 90:
        return "playing too fast"
    elif eff_ratio > 110:
        return "playing too slow"
    else:
        return "using time optimally"


def detailed_move_stats_table(moves, overall_avg, recommended_avg, initial_time):
    """
    Build a list of strings representing a detailed table of per-move statistics.
    For each move, the following stats are provided:
      - No. (move index for that side)
      - Move (SAN)
      - Time(s): time used on that move
      - CumTime: cumulative time used so far (MM:SS)
      - Remain: clock time remaining (initial_time - cumulative time, MM:SS)
      - AvgSoFar(s): average move time up to that move
      - Delta(%): percentage deviation of the move's time from overall average
      - Remark: "fast" if >20% below recommended move time, "slow" if >20% above recommended move time, "optimal" otherwise.
    """

    def format_mmss(seconds):
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"

    lines = []
    header = (
        f"{'No.':>3}  {'Move':<8}  {'Time(s)':>7}  {'CumTime':>10}  "
        f"{'Remain':>10}  {'AvgSoFar(s)':>12}  {'Delta(%)':>8}  {'Remark':>10}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    cum = 0.0
    for i, m in enumerate(moves, start=1):
        cum += m["time_used"]
        avg_so_far = cum / i
        remain = initial_time - cum  # remaining time in seconds
        delta = (
            ((m["time_used"] - overall_avg) / overall_avg * 100)
            if overall_avg != 0
            else 0
        )
        rec_delta = (
            ((m["time_used"] - recommended_avg) / recommended_avg * 100)
            if recommended_avg != 0
            else 0
        )
        if rec_delta < -20:
            remark = "fast"
        elif rec_delta > 20:
            remark = "slow"
        else:
            remark = "optimal"
        formatted_cum = format_mmss(cum)
        formatted_remain = format_mmss(remain)
        line = (
            f"{i:>3}  {m['move']:<8}  {m['time_used']:>7.1f}  {formatted_cum:>10}  "
            f"{formatted_remain:>10}  {avg_so_far:>12.1f}  {delta:>8.1f}%  {remark:>10}"
        )
        lines.append(line)
    return lines


def main():
    parser = argparse.ArgumentParser(
        description="Generate an advanced game score with move times, detailed per-move stats, and analysis from a PGN file using python-chess."
    )
    parser.add_argument(
        "-i", "--input", required=True, help="Input PGN file with move time information"
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output text file for the game score and analysis",
    )
    args = parser.parse_args()

    with open(args.input, "r") as pgn_file:
        game = chess.pgn.read_game(pgn_file)
        if game is None:
            print("No game found in the PGN file.")
            return

    # Build game header information with player names, game type, time control, and then result.
    white = game.headers.get("White", "White")
    black = game.headers.get("Black", "Black")
    white_elo = game.headers.get("WhiteElo", "N/A")
    black_elo = game.headers.get("BlackElo", "N/A")
    result = game.headers.get("Result", "?")
    event = game.headers.get("Event", "Unknown")
    time_control = game.headers.get("TimeControl", "Unknown")
    end_time = game.headers.get("EndTime", "Unknown")
    ply_count = game.headers.get("PlyCount", "Unknown")

    game_header = (
        f"{white} ({white_elo}) vs {black} ({black_elo})\n"
        f"Game Type: {event}\n"
        f"Time Control: {time_control} sec, End Time: {end_time}, PlyCount: {ply_count}\n"
        f"Result: {result}"
    )

    # Process game moves.
    score_lines, moves_info, initial_time = process_game(game)
    white_moves = [m for m in moves_info if m["side"] == "W"]
    black_moves = [m for m in moves_info if m["side"] == "B"]

    # Compute overall statistics.
    stats_white = compute_stats(white_moves, initial_time)
    stats_black = compute_stats(black_moves, initial_time)

    # Segment analysis (using 45s as recommended average for a G/30 game).
    early_seg_white, later_seg_white = analyze_segments(
        white_moves, recommended_avg=45.0
    )
    early_seg_black, later_seg_black = analyze_segments(
        black_moves, recommended_avg=45.0
    )

    # Clock efficiency comments.
    eff_comment_white = efficiency_comment(stats_white["efficiency_ratio"])
    eff_comment_black = efficiency_comment(stats_black["efficiency_ratio"])

    analysis_lines = []
    analysis_lines.append("Game Analysis:")
    analysis_lines.append("")
    analysis_lines.append(f"White: {white} ({white_elo})")
    analysis_lines.append(f"  Moves played: {stats_white['count']}")
    analysis_lines.append(f"  Total time used: {stats_white['total_time']:.1f} s")
    analysis_lines.append(f"  Average move time: {stats_white['avg_time']:.1f} s")
    analysis_lines.append(
        f"  Clock consistency (std dev/avg): {stats_white['consistency']:.1f}%"
    )
    analysis_lines.append(
        f"  Recommended average move time (based on 40 moves): {stats_white['recommended_avg']:.1f} s"
    )
    analysis_lines.append(
        f"  Clock efficiency: {stats_white['efficiency_ratio']:.1f}% ({eff_comment_white})"
    )
    analysis_lines.append(f"  Early game analysis: {early_seg_white}")
    analysis_lines.append(f"  Later game analysis: {later_seg_white}")
    analysis_lines.append("")
    analysis_lines.append(f"Black: {black} ({black_elo})")
    analysis_lines.append(f"  Moves played: {stats_black['count']}")
    analysis_lines.append(f"  Total time used: {stats_black['total_time']:.1f} s")
    analysis_lines.append(f"  Average move time: {stats_black['avg_time']:.1f} s")
    analysis_lines.append(
        f"  Clock consistency (std dev/avg): {stats_black['consistency']:.1f}%"
    )
    analysis_lines.append(
        f"  Recommended average move time (based on 40 moves): {stats_black['recommended_avg']:.1f} s"
    )
    analysis_lines.append(
        f"  Clock efficiency: {stats_black['efficiency_ratio']:.1f}% ({eff_comment_black})"
    )
    analysis_lines.append(f"  Early game analysis: {early_seg_black}")
    analysis_lines.append(f"  Later game analysis: {later_seg_black}")

    # Create overall performance lines with additional analysis sentences.
    if stats_white["efficiency_ratio"] < 90:
        analysis_white_sentence = "This extremely low clock efficiency indicates highly aggressive, instinct-driven play."
    elif stats_white["efficiency_ratio"] > 110:
        analysis_white_sentence = "This high clock efficiency suggests a very cautious and deliberate approach."
    else:
        analysis_white_sentence = "This balanced clock efficiency indicates measured and thoughtful time management."

    if stats_black["efficiency_ratio"] < 90:
        analysis_black_sentence = (
            "This low clock efficiency indicates rapid, aggressive decision-making."
        )
    elif stats_black["efficiency_ratio"] > 110:
        analysis_black_sentence = "This high clock efficiency suggests a very careful, perhaps overly cautious, approach."
    else:
        analysis_black_sentence = (
            "This balanced clock efficiency indicates a well-calibrated use of time."
        )

    overall_perf_white = (
        f"Overall Performance (White): Averaged {stats_white['avg_time']:.1f} s/move (clock efficiency: {stats_white['efficiency_ratio']:.1f}%). "
        f"{analysis_white_sentence}"
    )
    overall_perf_black = (
        f"Overall Performance (Black): Averaged {stats_black['avg_time']:.1f} s/move (clock efficiency: {stats_black['efficiency_ratio']:.1f}%). "
        f"{analysis_black_sentence}"
    )
    analysis_lines.append("")
    analysis_lines.append(overall_perf_white)
    analysis_lines.append(overall_perf_black)
    analysis_lines.append("")
    overall_summary = "Combined, the rapid and variable play suggests aggressive, intuitive decision-making from both sides."
    analysis_lines.append(overall_summary)

    # Generate detailed move statistics tables using recommended average for remarks.
    white_detail_table = detailed_move_stats_table(
        white_moves,
        stats_white["avg_time"],
        stats_white["recommended_avg"],
        initial_time,
    )
    black_detail_table = detailed_move_stats_table(
        black_moves,
        stats_black["avg_time"],
        stats_black["recommended_avg"],
        initial_time,
    )

    # Write output.
    with open(args.output, "w") as out_file:
        out_file.write(game_header + "\n\n")
        out_file.write("Game Moves:\n")
        for line in score_lines:
            out_file.write(line + "\n")
        out_file.write("\n")
        out_file.write("Detailed Move Statistics:\n\n")
        out_file.write("White Moves:\n")
        for line in white_detail_table:
            out_file.write(line + "\n")
        out_file.write("\n")
        out_file.write("Black Moves:\n")
        for line in black_detail_table:
            out_file.write(line + "\n")
        out_file.write("\n")
        for line in analysis_lines:
            out_file.write(line + "\n")

    print(
        f"Game score, detailed move statistics, and analysis written to {args.output}"
    )


if __name__ == "__main__":
    main()
