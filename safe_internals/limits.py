"""Apply Linux per-process resource ceilings before exec (inherited by children)."""
import argparse
import os
import resource


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--memory-mb', type=int, required=True)
    parser.add_argument('--file-mb', type=int, required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('Missing executable')
    for kind, mb in [(resource.RLIMIT_AS, args.memory_mb), (resource.RLIMIT_FSIZE, args.file_mb)]:
        bound = mb * 1024 * 1024
        resource.setrlimit(kind, (bound, bound))
    os.execvpe(command[0], command, dict(os.environ))


if __name__ == '__main__':
    main()
