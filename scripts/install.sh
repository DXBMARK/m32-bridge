#!/bin/sh
set -eu

# M32 Bridge POSIX user-local installer surface.
# Official targets: macOS, Linux, WSL, Raspberry Pi OS.
# Safer path: download, inspect, then run locally.
# Download options: curl first when available, wget fallback, or manual download fallback.
# GitHub raw bootstrap: when this script is run without repo files beside it,
# it downloads a source archive into temp staging and runs the same runtime there.
# This is a readable text script. It creates only user-local files unless --dry-run is used.
# No binary installers, ports, or background daemon.
# Structured output includes admin_required=false, hardware_verified=false,
# production_live_ready=false, and osc_writes_sent=0.
# TTY installer wizard uses DXBMARK style; non-TTY stays plain and JSON stays machine-readable.
# Post-install checks: m32-bridge health, m32-bridge setup, m32-bridge get-info,
# m32-bridge detect-device, m32-bridge doctor-runtime.
# MCP guidance is manual-copy only: use m32-bridge mcp-server as a local stdio
# command; this script does not write Claude, ChatGPT, Gemini, Antigravity,
# Codex, VS Code, or Cursor configuration.
# Lifecycle guidance: update, repair, and uninstall stay user-local; retain saved config
# by default and remove config/audit files only after explicit confirmation.
# Idempotency states: fresh_install, existing_install, repair, update,
# already_current, partial_failure, failed. Partial failure includes recovery
# guidance and never claims success quietly.

DRY_RUN=0
JSON_OUTPUT=0
PLATFORM=""
VERSION_SELECTION="${M32_INSTALL_VERSION:-}"
CHANNEL_SELECTION="${M32_INSTALL_CHANNEL:-}"
REF_SELECTION="${M32_INSTALL_REF:-}"
LOCAL_SELECTION="${M32_INSTALL_LOCAL:-}"
TARGET_VERSION="${M32_INSTALL_APPLICATION_VERSION:-}"
# Keep these values in parity with src/m32_bridge/installer/runtime_manager.py.
APPROVED_PYTHON_MINOR="3.13"
PROJECT_PYTHON_RANGE=">=3.11,<3.14"
UV_INSTALL_URL_POSIX="https://astral.sh/uv/install.sh"
SECURE_BOOTSTRAP_PAYLOAD="H4sIAAAAAAAC/+U9a3PbOJLf9Ss43NobKiPLcpJ5nGo0e4qtTLzrV1nKXHY8Lg4tQTbHFKkjKSeK1//9uvEiQIASJSu7t3Wpiizh2QAa/UKj8aev9hdZun8TxvskfnDmy/wuiV81XNcd5pMovNlL4mjpZGS8SIlzkyR5lqfB3JkmqZPlQTwJoiQmzumrl86bNJzcEieMIT2KSJq1G43RXZg5s2SyiCAjc8jshkwmZAKF8sTJ74hzcT48/uBAO85F8pGkwzsSRUUTTpBlJM/aznEO1RvkE4CRQ/UbAv0TqLZ0JsnHOEoCbHSeJn+Qce5kySId0/4C2hl09fvvF38fvTs/u+iP3v3+exuH12hM02Tm+P50kcPYfN8JZ/MkzaHVOMmDPEzirNEQaentPEgzIn7fBdkdTI74Gc6hp5RkmUj4I0ti8T2Rqamsn90t8jCSv5LxPcnlr0xm5EE6DSNZKyezufY7mUUKFIsUf7VJmiZpKS0l/7Mgmezic8jaoTMwCfJgHOFMZ3IKskk4zltFlixJ8nBGRDHxm+XOgxznRGRewM+WcwFTe5Fk4Sf8ycrly3kY34pi/XjZcg5htYObiLSc02COuawkB57OvFMM6I8kjFv4JZtHYd5oNH4+Hr17/8a/HCA2jc4v/+70HPfow5vT/uXf9mevXu7dUNR0RcH+xbF/eX4+gmJT9y7P51l3fz+Yh+3bML9b3LTHyWw/JfMk2380mn5yze7895cnWltKO6taQDh+GVwOj8/PEOKXnZcv9w4O9l7+IEu8Hw4u/f7PgzOE1f0AQ2G7bO/08GJvKPff3rHYMW7jtH92/HYwHPlvj08GZ/3TAdYsJmEvJREJMtJGFFVKDw/fDU77KjgHSu7F5fnR+8MSEA4AoZQ57X/w3/x9NBhCqYOXPzgvnIPOy9cNTKYTPhhenJ8NB0UZyNUKXR6+O/6lyH/57Xc821Zq8OGif3Y0OJLFvz14uar42ejymDXb8TudDs28HBwdXw4OR7R6A4EcHZ8Ozt+PKHTtTuPo/L/PTs77R0r6K0y/HJwM+jAU0YD/7nxIWwG0/UxioFlew4F/j/QT/7nJDdKmjKPYIiPpOIlzEueIJW6rKMjXZ4+TvrXlWQGxrKsrPDWajf5wOBj5iBgIMIPQneMW9RnhdLsavrDENpCi9u1n3o77MYyB8GYrawCREcVZ85KsY3n+o53dldu0FptnB1DuqeGPzi/8k8EvgxNfQfTBydHq2c/Gd2QW+A/AlYCuq9MHTGOyGOdqEpCgKBxTDmCrwWfaz4NbW/L4DhgIidQsNiE+rMMszPU6ODN5ki59IGcaWIubKMzuyMQPdNgoVijL6bP1tMzBoxsHM+K2HJe2DWDcBbCn3CeoNOr/DMgLxVOC6DEHZsDmLHUfvL90O/+4Otj7z+urDny8aP7WrpPk8vqQsVfO/MdVf+/XYO8z/cm+7ulVzAYr6jRfNP+i1vtGzf6GtqSlYPnffnVxpjhtMwbOZwP4TJ6TNAZmOUseyDwl0/CT5z64Tah7eH56ejwyqqYudhbsTa8fX3eeoJ8msCPKMZ03QlYaID/2Lhcxskr6o9mlA5iQKYgfYRzmvu9lJJq2nHEyIV0QrNKWMwNxIrhlv5rO3k/OGRD6rsSEbDEnqddsywam7iPWfuo6j7zqE0Aji0PzbcwH+PGPnsErQB7/BqP4L8n8PYZTvVG6IM3y6C6iIGZQ6XuMwk3Tk/suCo4RKwSS1SIrMrNFOg3GpEiYwF5IF7FShcsusBUAVqChWuMyyb8H8lGkl3YjzXD+QedQy4dNbORp21XpiiUDWhRpnDxxOlikz4I4nALQfnm8RYY5WyoMQTq+Cx8QfjK+zxYzoyH4fYvUwaRVZls1yoQT4BRhvjT7YaMW8AApqcxj9MVsWtBznxIv2cSqMhVNydlDWbNyzqyZYvUAb408ZJZ+lIyDiKEd7APEddboZBbGPuJgmJKJzH8bRBlveAm4OfOZ4uSDrhNOQ2vBmOQfk/QeVj7g8w/SFKgaiO6MogHDzpIIBpAmN8ReJMnG/sc0zAnwXlixLmpSUKhDM++CdPIxAF0GVrkKCs7vEBcinKyUBJNlqZykTkHmoyJAiROlQfjripInkNuvC2qUEtChYq43sOJrSYh/SWC0C7qf/09t9KpNrfJktS2YNxNDrbguSjYaOLsPQRSiCuUrMHqQuIA+mbhI5xyqs/kJpw7gAui1FMB4TFjhFuMQoJDTn85XPfalDcnh3KM5EYlZ4abzEwrnysoFIShXJWblCgEXOePx2S/9k+MjlCAuGaCgl946s0WWgyLu4LCgo9kMNO2HPcY14euQzH4hHKQ2Z0QwAFDZvSSdeLBcaTAGdtt0fnRevUQYS8k91CK+p4YGmQpLw1ps7mAAKB4HMJX0SwroL7vJSgCb/Ztgee4+dvDbb/j5Z/z4C378CaQHHJyQMaaLKJoF+fhOLEeYlRj7sxcEl32cm2shBsX3Ku2/jInchCLYxP8RbATt86+oZQkBTpmAC27z4QDbsfIL4SBd10Ko3HpttxgeX2O2sHsojQJ7v4kIyG95gFR3xWLHSTqD9f4sCN/Wi1wXZ4fn7y8PB0KEVkY3ZIY6BoYcG06jc0c+BRMyDgFSZ/iuL4YjYZ84Aq8itBt6cnELSV1Zj6LaxhtuG+Bfd/YKdKkYCV+YAjKxFdlK+2gAowxBMC59YYp1NVkI/G9eHXSveYspslng9NJ4yzS9Fy1DAGcpySKfL3IuKaHZDpiXzLTIj5ypsXwLG9byhfRsy9NEfyGMsCw0Vvm3BAASpsIrJoZMoyTIWygFXTOZxNbwzRJmyFYbqvEmoDaWyqz1GS8XlmallXa73aJTZFSjq2VRkgBD+YyzjRU7j8w6gijFLSDu0zrkPD4bjvonJ/7FSX/09vzyVMVL0bzASNo6kireeoGAXNoCmK/QUkDJHH5pcdKNXA30X2EBEWvfbAGzk1YOseI0FVYXUuATmF44Zc1ci3Ej1ZedUspfd5hD2IuHIySNh+dnb0+OD0c40PcZkvloSWk96uw54VJikpr0QgiIMFpPfIXxukDWYCXdpuBPZXoiEF5VmBVBFAV0MUOKNGwIsoxcWcQ9Pqe0LonCKd0hKzrjRqQ1fWnFCGyjoslwapsViYx8PlpoGSMcUvw1A1FJRcz1q3b4rn92NjhRcVP0VrAxZvUvumrhomBfbd14oc+COYA182GpwDcBpY2oZwkSQ7n6TbKIJ1CYGVN9epwjyy94o76grLInrwLknv6ztQraniWtqMDxpcf/qi1Noea0SBDj6Ykxsiy++WHNYARIujyF3jfb5NM8iCeoEMNW4DU9Jm30KD0u6rdn95Mw9eagcMZ5RlW7lkM+haD8JPdc0xO7qJi3tq5doYjFTdhyX1By6xaoJnUq0Kao+U22ZWpbOprnWt06yCvYfnGqcTwcHp/9zIRtOh0ToVPiKSB0IvtgfEJFXNk75S1IegQr0rCMHhuxMk1PhbjlmKcrLad8KmH2Z6M2Is/TZkGHsKXlAS4A+gF8CsHqKbOvJOsVOd5MfE3BVqtqGeXKAv35TrV1ybOKmpY5RzMQogui+r5jHIvJCgx37skS6WbpYEPl170i26U0tXRsUqCeNGaVGi1ONmq1WxTXYUUzLR/klTgQuL6Sw7i2ALKingbttbp/hDxWWh4qeGqijY5Spi245x64LaMMJxJmBjNB9uSJyhy6YHYqSyt8Fnv8r1mAj6KiLzsBVvBtBS2uoPUqmleQ/aJ3DZ1rYXq5bt1NaRi8au5H3fS9QSWd0PcqWYBZs2Q977mCmE3cVYV1nCtQvXT4d222UWFt71Hba+Fh4nNccq04W2GO7xV6hNalpaSyOy1HkBa4S1Z73DKc8iLgoPuSNGRij1u5qIplv0eJwhU9L7xeW4HZ6EUdfrh4XYkHqv2/V0qr7NJ+LmBWr+5dYwdVa6EcHFQUUY4PLCUquE+bWuoZa/V0TlvU4J0XnIoPiR7eFvRYYiHKqrpCirKE+C5YLi1hqayT6urJ51BVCAR1lp4KN0G6lHTcrWisNjUq5ox8yql1ZVLMmivTCm4prJlc2s2CKfF5MYHFnhho0aaid7BNLYxvKHrCDJdtpFovAMh8yVPa6J/lqlDzERcNGtYe4KmenZo3mypvRmX6sdxgy1lHQUpDemqiffZgE8FYGClBLj7tjw7flazQBQgt6tXH+pOuebzfzJmE02lhkq4nWKwTKqwChSFMABOLwtu7HNFrHpG8jJcrBQohTCimqV1JEttJEdtKEJtKD9tIDhtLDdtJDLWlhedKCpVSgjhudQ3Uq5IJ9G1Y6mbD8oYQUDX+jRj+Fsx+W0b/PCavM3ikn1pK076GsjBPaNpRF9k9llJpfFPlSPzcnp4B9MyjlSq8b3Lb+3QafkINkTrLrVEKhQueenTNLCJT99Hqk/q0z0e3/8i6fXpkXT65jSod7wuTYQZHtUpXi/qazf/7El9TmNRJ7RrC+gXJKKoQnBZRi3AtWmoO53m61UZ6Vb1SWytNFvpZbMM61NMCi4Vkri9V2dw6ZWeNolOt5DQbVlVlarr96hRma61F0ViUOXYUaV1XRSi4is4hfG0NNUOlvzXUiOeoEDtUH1ZT5VUU2aDGZUq8Sh6upMYVcvBzyPDmJHgb8ltNeleT3RUkd3NyW5/U1iOzawVT/2bJByaM1a3GM6TUTcrWkk5rUtY6VHU9Ra1FTVdR0hoyZA35scndM6pOEYV/hun32FrpLVnpp2F1wNjUvYJ7Nhi+myi6lk5pi1PoroVArJKZp4VVQBaT0yRL6S0VlL5nZsmzUPHFMDsoA/IK5lF8Y/yFfYpWxbkl31kcCwo/M8uE0FP07vrRsYLKmFjPG46DN1L+ax8FzVwFO/cM6JZpKYJfPm30BIBeoZuIW3dP++Ku0n4EVTKcXuXuFZ552m6MNVsO98L2C3cB9Uyaek9Y4BbafAE4ekvW8cdYN0hNeKo3Yugj23+Ez6e6o7YbTZF/aUaa1XOg+HKo65fNk5iOrRbwf5kDzZwDme8ddDo1wS+fxyuehKL7lhOFWd7cxAgpO9FcJcUQi4EJP5OAdqFaG2GibtFhsktzrnS/9mt0iSpM7+gXFeZkhg4yomkd2jxddo0jA9FFG9gliSeeiT/YqBWrqfNEs7TyYzLPSzNidoq+zGG8IOV5l+PdYJbPzkf+2/P3Z3R6z5LC/13x16G3rB+CkDIN3Zwr9s0s+OSJ7lvOPVn2omB2MwnonHYdv3CrF/eJ6cRc6XfgrptNizPTVn5jcbaY411i6smhuI2hyMZHsIJCiPuzuFtcSPDpQQ2HrpKgU9N4PWpeOKqp25Z50ShdK3nUqRVxhluKOKVuVPCF7b2Pans16YL5Silco2KrhfCSpG33GyqKq/jTYwcrtKCBWRaxrxAefTPNk85qeC5TIc4V0gy/0PeiQABNAttA+ir7ANej3wwSYDsAy9MmdHsVzeYX9akTPBYCrZjqxPPQFyK/LM0QFi2/wMRdCY9b24PcRu8P2VaTk1DcpZU6B26LMKa7WGzslaZaBVhQCsSehlkQ60aPtHgTX1naEOVqD4y7leuHadzLjPczSUjGXdny8Z3itsvyS/7kLFHgosFxuKs/Dbqg4GP5dpRwY7bwJu6drZWrvBpWeX0AC69EHebbr+ONFKKehziXZSmhHuYIf2YG1CQNpjkjvDgEKoY+B6gjbE/QxcwZ0yAkKLoIbVWFw1wVAQddFERSBdQyo8BylnXdwYwKzlWNsqxADS6rwF/msTaBQR2uStvNLYyt0xnCv7CHtS2wgznAZivHD5krLuas4DRdQW+LHUaZj+VmCHPso9ZGRVrg7n5VdJ1lG5L4Nj6ymmss8ztUhW9JSiWAymiplGR4ajb5zUqYS+pEe0WFcVUq52OGcSljYtK15FO45pjE5oMhFOpGRnfahQXeK/OTYL7pNOGqc80aukmTj3h9WJqyKblSMWsX06m7GOMunoVZhmF0ACSc60UsJ/b95UkJyURW1b1T3TV4kowXM3q32MA5dhMIPhVvYW6nsjkL26xPNs9gW7mSE7BepJLh8EhQIH/TtZADE2NS7Bu5xwrTtaoOK7Lx6ik04VSs2jQk0SRj6ihldtGS0wZm15X3+w4UKs/A4+KI7phAYa4K3YMXLJWqIsCJXocH9NnJ6PgYoF/el517qkCVAp9Q2KxH2DsBsB6DV7yyqq7DqkOwOVg11/I1fRKKQDLNdeKphg1aPJkVbFHDAztftN03pMthXHza3C9MWYBK5qhMo+hSwRkbVVG5t3WObZWaOxmHlbmXLoUoPD6cVhC8dXqEvdZztAo5hCqtgo+CXYxXFYvCHGHDXXEPUA643oWypx3ta13utJIdeduvZAeVsrDn7rkIKgwdb802dwKawNMyiJMwC25TQkrSvMbrVs0bwxxe7quehVHuAvoKQZ7Ze0w5XoqcGn2sJ3FKTRA5Mkuk5Ad/KqHKdrMqTHq6J8vMCVLUrcSZNwKwiO9jEOIsV0cZWF1F4ii+wQe1Fz8+NYStGNpXVGt6tRZWVBlMG+XQzFPGRAXZngh3ifMHjawynjPhVps8TGLCjBoSbKtLb8XcTcuT9wiAPQmBhk2ituM4uIakrapadEq4+K7o+AyfrTqBVnWjowJ+fx9ECZUeVgwL4zjyS9AWYsKoITtih8UqoOeOiavWS9QrwmOkRAlQoMQR++71E71Vzcpb4hXsch3lcOyjNfbAFd4RQ2xny9rVF4aHmus6zH7PXD1l3Lmu7O1JVU6qo/R1q0RcS/i+riHargno13UMVwVNIOs6mmHaYHhdx7Bql+SyrlO2X5fF3q5d5q0KA9jl9LVsvzbDA3bNlRMRA0VMCMs243ZqXEmLXaEy1IQk8LhrBNs3tGqMmPGuD3gwfH86BIR8odJDagUBgvi0YVSO0q6W6jJDcbGNEaYgipKPe2iIKCxpHAGrvWelwVEo9+zkdv8RW35y+VxandiYKi3CP/H4FrD7wjhgnhrlwBplNdqMgMZjWXAXN6XdkoubkoNKQLKAFHqSAPu2fHW4xU0rn9itJBFOzAjHyiODzElMUmo+1gNd4GCkxVdASAUu89S5MEpj4MIwiHwTGeG/cp6tNWi4lJjt6f4YokHTFbD0u/75Ise+N3g22gdkuRxg/J7BETtdpFKECEItYC9MnuktkVfvFYxQs9vsTn2dC/aUJy1SLAGNigvweO8sJ7EMDDcJb9mtcB63us2wy9MigfhseaEU/4IykRY+un2zCKMJL+f5Z8klAQBhDj2h+Krn4B9DwHA+IKziuR9vgMkHGY8wo3O0KWWJrDlYkEVM6UgaxLfE02P1fuMcNLtVF3nZJKgwX7K/Hp+llnNH0K006z1iBJF0r38LqQUpLiIuPzWNTqzn/KWjOH022ch5WktsyB7/a/bAj/nVUN7td6PRBcU8nDsoYAeBastjFuNTUOFXnYOW86rzEj9e4cf3+PHDk2NO9k9s18tptnci94Q1t0BEuSlRCec4UtmgWJnKAjguvmpM4DpJGDd3m9WVpC+w+LKq/ZWEobqi8I8trmrAKnCURx7RJvEkw33gsRseTfV+v2tvt2mf2rJfh7bL7F4pCmaoh5tID6mszed9zUpvSP3kwgsKKNZflSvVfxGJb1mgBgGjttSHLIj13gktVtEGM9ZjM9TKH+ce+4lRhgrmtuE4V5328OBfwiEedy0BfUj6tkehYkExluwujAj116gGaXwH6qg6Keg77inRzZuVVbnyQVuo7oBuEWj0vrKEYCLf9OhJCG1vZa+iQq05/xfMe8EJ24s54ui6MTE+xW5xryprzqMuRWy/n4b6HmLj48MuBNk1vmGcIC3iKIzvPX5wpIsQOl3n7XkjxqVocy3+SkVbsC6DGW3SzapFPz95T322uIhqWXa53AjLBJcJZsKhT0YARNoQNEYKQj0fi52/tpzzoRhsFrWHQ1H8F9RPWOjuLzbsdbguBz0NgHxM6FWUaGkMXNmHIC53/glwHhUvsGQ6yPTFl3m+tBn0mQRK6TXfk3fkE/vm6dYirgntdiBCuzl8Nzj8G6ikmhqpjEgMRRpKSiZRccJY0ikZjFxBXHVpiAerVrRBeiEDR1QOwFjStIrLWFSVUNuzqRpqq3I1+FRSnUKzR7L3adrpLE8J8VgxTUOpqZpoAjOGXmVQGsIRv9pakuvlpEF2cctKhUbqiFUNU6mrolXIW9VqtpHNTSDU+7Nh/+2g7Gda2hhTtM7kNcm3SZclleLvA7VHQcpT+Ms+7TfB5Ndw/ha+mhRr04EMjV3NTYXMao7obZChMWxsKgdShw3Nzs21W6t7Nceu9DZKbrzqSBp4rKM0hdfmsnTs4t/Zq5c+f+6n2Q4xfnnqMecPqhRhJUjNljNKPViTzONjEYegpeElP7pm3qMcgz0QHgsLLMog9MWgn5qqEwlruRxr45nLQJ0JeAxrGgJTOoCIYBs0SJ9OlxgkV50iNqztRmKJJOl2QG1LC78KmDX+GFUbCWfmUZpDaRGVXP0cNp1HYtBOgQj13EU+3ftBnEIbaP0+DlGNFUjOGx6dn54cEZlRF69FdOXTwah/1B/1NRbLo5NoeKbbwnW0FlPbkyOXThaYXnnaxfOVExt5LUUo67zIpsGiFWch+2i4J5ZIK52xl+MIV9xOvZLgXktHZ0uMTE8aPEumx1bJxkhRqh8vNTdRnxpp6V3EUJoBn2OL+znM3y1u0N+ZnuyE1PKUhRPN5bNsoVtrSJIAaXcTpVVJ4xluf4y4jS8ZKYcQ+w/xhL/T9A19hku3BKyxS5UKf9hjw9zrz8O9X+TphvnEWFHvSQ0FKq1+z7b11bJ44a61myuqzBRG5M5tTROSQCp4UWWdeI5VYktrxOaStzYOboAUKnEWfiZ2dXgeLKkeUTYuSNCohbWxuTVStUCC7vG683rr20aX0mVWOFAgr2WuKx8DJoBPceMaFNoKyKs6gIhDoP5o4J8cnx6bRCRFPs9U8HlKHgABKIDyvncFLK86HefHXgHSjwBRpw5ENWmbwGF2Hk9PuyjVIfbZ2RjPpnpnyDBg3IgHzqMY1FOlBr6ZEWEb6wCHTonNvLVdYAv9f+ttK7fsWoUeZUi+aytoyJemHRqx5zIDci4u7XHg2hMqnnl28U6X6mjtvw7Pz7YQ6WqPi6PqLIhQ44Jv2KE2wyVZRonErMgyuuxSlm2oLKOsR80DzpJTS6/C7d083NuWYW97wvZFT9aMEzXlJG2zE7TNT85UNrHytIw58mkz9+O607LVZ2FyylYdbdlCaBpnVW7HdV4AQ2kVh1HsdKnZqHWGtI5p7+jewnqm/bxrN7PCJ5RhKyOq1p6240zbcqdKCKuZ1LaMakugN53UKk615jhy42PI5x0/KsD/m4j4K11XdyrX15YrvijQXI7gEDS2W/LT8jJbzsjKt2FX8mXztrYvPeIs114L30yNldE3yyeMZ9JnygufJpqNT5n3eKk2/tJl5uWcbC16rpot3UGOG0WqjF1oZS0NqE1dNOmrbuyx8yLYMjBZjxe6S7Jc+Pi6rnxSp52yN3bcNvP1dYtn0rVmeCv4CAm2YsmaA/wfk3SiZeGUCscXdnv59etXT5baQMvSpSV9mga3M9UyjeD/9hu9HCA7zu+07D9bc5s7XyNhuKK3x4QBo2y6AjCoG74CTpshn7vvNnVtIuV+9t/zCcizq4Put9eYdOUefXhz2r/8G40ZJAP84S/hEYnfxYGke7270Sp2Ofp8h+WWls0NlcH/7TW/jsDMiOimvKUbqpgq1u531wKvRMuI67o3O7IBWbrs675DdFjl01pF5uz+kBY6p/iPlmhb9b00qxPlCurHwkPSY6HHqbtvut6aQWvl2/NO3Qp46vf070jDCn6we1KmUAXRuFiM5xMtHo1DHE7VpVollDU1JI6lEdeK9MApL1old2i7K7T2xqF+mFUc31Fc/SMJ40I3E51yFKjD5GV7dVl9wd53wt25CLSGsSNu42NU9VFdIYjWHWRBeQuqr2DTFtzdyUzQoeIFKQbxitsAMDpamF6+o4+B409sTP5o02+ThL2FR5/wCjN/noYPlNzOfUABkgaRh4WftZ0uWJvsLncyvwnG94WAm5I/KJIrkK/xuRdj4/Ne6H7MfOG/Ox+Ohs+1SBdxVdS5XzHjatgasW+24TYykb/4VcElHr8GtvB1Kcj619xz92vmmfs1YzVfP0le4mrI8RW9gTAh1NqpkP4yfVUlAJpQItk7ILVymo2rvEKEanE/k5Zy3bgcLkjOO6fEliPYgmxi5J9/kq5jWJuLF+y/OEuHsbf/RarJl1FByjMoFW9FTchReKVOU1OMtAQ4ZN1EBc+uCtrEo0vNgvQe7wqZuLP24XCrL4Dx7HvFoFi/OCMSG1lVNjUc+KoQQhR4Fl2Ep28AMwtCVDif/bqbOFUUVi6JIEQWpci+HcUQ2sj8wyxh1IBBftXdO7h2vnHcbzqdbqeje6JtLJQ8fxiG5YEjZ/45jKfJpo92bwQHd5DB75+hjxKFZHAIvNGjynCUWRMmZ1V0NBOhRLwiA9OxBY7KbK3QmUp5B539lmdv9tYpulJOxwJP2XGbN90S8KMUQmKRjKZC81nSndzPr3kAKaP8KEeQHLh/9hHkyuFg22vQvDTzbGTcTWw3MTLwWQEZBxd0mZs/FFs4xy3WrUDyapl2rSgQTCYpyVC5D+f8exva4F9pG/yhbffqurQ6BdVZT+Wxe092IOFFTFVSpehcSg7je5+K8qUM+EvSB2bfUZIXcQaiHA2kL7kf9emekdkNDYkM1F7aiFtO4bhtXo7F9ZYyCGfstOrWbqF9cRcmzqutZvNFSj3F4c8Fng5eCJALzQ6ycLDBDfWiIB7d9kG8pMY1phVhd2360Qb1Z8oNh1T6wNrMqLjTkZBsHMxBvOXe62I4yr1Z/nRHG1V3uhAvFFgsDqtFTbtXLz4dAdkPxM8Tj7ZsLbYbfrnlHOhURPCHYmSFiGa4zzO8FO7uCpYW7FXc26V+5PTwXTrJu2kXvfRxlHegOajhpNleyOgdY8zBQzSe5hmHTjyDcZLiqvngbHR5PBhSfX0xw4Mr5uWN7KDldJqaq3hVGx8u+mdHg6MyV3rWYnC2xOcTsY4yp0zVZBE2BpMCnd6/jrYmDWHf2R0GoZTsoyNA+XICn0pePsyy5YztV5kSoXO7ljIhD6WUaThNvOamp5TV04R0NaPP+pCHcEwKd7Q5SWd4JWnSdqvHQB31TWDUDVvz0ol2MUQZbUTWdbDZvXvz6aQC+zmq0E4ZCGYdtESwatYYL89dDo6M42QRscsPN4T6+9uuR9I9z5+p0WZk/cX90pWhcTJf4qhBzvBEg6xac+sbkvXu2AQq6Wyriqpx3acuFRS3afhVGvnQSy0CiIoLGry2JX+U9GH3PhWH/3/QPhxvPfq3iMNP/oy6LTmiNgCJhpnID3LQv376yTn4run8h9NJDr7vwL8y7VGa6GGhl1hod/SQXzLakA76FYRQg1cYkzrAFpPOa4T7abfUgxkX8SA2X86romHthEjb6ED1YA86X2CwVL4HdQCxr8Zy7Y5tUCrD6QUltZxXIIH54uS40RhHAShrqq9oycUTHShF3jsKpjDNsttj3CeSF/cyEk1p0HhuBJzO+RfUr7nz7CwTgaa4uxUvEpOPmrG5ZO9hQi4mShseWmbwch8UBvpAf7b76S29lnVBM7vFaTR9gNBeCsPwjIHY0Pcv3CEZo7KECvkkiNDb5/TVS+cNdYEoovpwDHOV8+60DTqjH/CmPXdvj58z0HBuCUpEPU+E/ihedy3eNZooSFLRIlu6PdRL3E3qyQC1qwqJ0GYquNYolOIpqebK5lIyXd3fJF3u0Rc/HcZYetBbkoLiBaOxGOFSvvDYNXDi2wf+dg9GYLQ4ZoXiBBGKIleW+NKmXxCSjDZjM6FGAXuvkT3lIZfbs75Viy21rQ/WsuViz8DRUkqCXlI8o0dLWZ95Fo+p0BIVz8pOWS58sT+cS3P5D+PpKNstZEOfnafo7Gg8fNWeLGbzzAzx82ilTWagP+MRYVk0uYdsy3PrRVv0XUFsg3mnVjVEPWh9JEQ0bCFzea4oOyNZFtyKgvxXRdlgMgtjX2zFdcAuMxDh/Pkyv0ti5G7s3fDVlWKSf0zSez8bB3Su8LVI86VcWXycxIC29CrnDalRPsnGPg1xkvkZc9jvVJS8C9LJR2BvvnzwfDXgPDgjhl2M0KLCHnyurPNkJgGNBJB6L1sWhSvNfYzkankNutkwv3FKctAosFhBXNzw7QBlL7wv0Sr6LfXT1MhSBygSSCo+dfLyfXr47tOH9Hyfn74ziWRIl33wKcw9Sr2gmf8FMhrVo3ipAAA="
SOURCE_URL="${M32_INSTALL_SOURCE_URL:-}"
SOURCE_REF="${M32_INSTALL_SOURCE_REF:-}"
RELEASE_TAG="${M32_INSTALL_RELEASE_TAG:-}"
SOURCE_COMMIT="${M32_INSTALL_SOURCE_COMMIT:-}"
REQUESTED_SOURCE_KIND="${M32_INSTALL_SOURCE_KIND:-}"
USER_CACHE_HOME="${XDG_CACHE_HOME:-${HOME}/.cache}"
DEFAULT_UV_CACHE_DIR="${USER_CACHE_HOME}/uv"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run|--dry_run)
      DRY_RUN=1
      ;;
    --json)
      JSON_OUTPUT=1
      ;;
    --platform)
      shift
      PLATFORM="${1:-}"
      ;;
    --target-version)
      shift
      TARGET_VERSION="${1:-}"
      ;;
    --version)
      shift
      VERSION_SELECTION="${1:-}"
      ;;
    --channel)
      shift
      CHANNEL_SELECTION="${1:-}"
      ;;
    --ref)
      shift
      REF_SELECTION="${1:-}"
      ;;
    --local)
      LOCAL_SELECTION="1"
      ;;
    --release-tag)
      shift
      RELEASE_TAG="${1:-}"
      ;;
    --source-commit)
      shift
      SOURCE_COMMIT="${1:-}"
      ;;
    --help|-h)
      cat <<'HELP'
M32 Bridge POSIX installer

Targets: macOS, Linux, WSL, Raspberry Pi OS.
Default install is user-local:
  app:      $HOME/.m32-bridge/app
  launcher: $HOME/.local/bin/m32-bridge
  checks:   m32-bridge health
            m32-bridge setup
            m32-bridge get-info
            m32-bridge detect-device
            m32-bridge doctor-runtime
  managed runtime:
            CPython 3.13.x installed and launched only through uv
            project range >=3.11,<3.14; system Python unchanged
  MCP:      m32-bridge mcp-server
  Lifecycle guidance:
            update, repair, uninstall
            retain saved config by default

Recommended trust workflow:
  1. Download https://github.com/DXBMARK/m32-bridge/releases/latest/download/install.sh.
  2. Inspect the script.
  3. Run it locally.
  4. Copy MCP snippets manually only; this script writes no IDE or MCP client config.
  5. For lifecycle actions, review user-local app, launcher, and config paths first.

Options:
  -h, --help        Show this help.
  --dry-run          Print intended status/actions only.
  --json             Emit structured JSON.
  --platform VALUE   macos, linux, wsl, raspberry_pi_os.
  --version vX.Y.Z   Install one specific official Release.
  --channel VALUE    stable (default), prerelease, or explicit main development.
  --ref FULL_SHA     Install one immutable 40-character commit.
  --local            Install the current checkout with zero GitHub requests.

Unified install methods:
  DEFAULT             sh install.sh
  SPECIFIC VERSION    sh install.sh --version v1.2.3
  PRERELEASE          sh install.sh --channel prerelease
  DEVELOPMENT MAIN    sh install.sh --channel main
  IMMUTABLE COMMIT    sh install.sh --ref FULL_40_HEX_SHA
  LOCAL DEVELOPMENT   sh scripts/install.sh --local

The customer default is the latest published stable GitHub Release. The
installer verifies tag, commit, manifest, staged project version, and checksum.
No administrator access is used and system Python is unchanged.

Bootstrap commands:
  /status /help /contact /clear /exit

After installation:
  /health /setup /get-info /verify-device /doctor-runtime /mcp-config

Status colours:
  Green available/success/safe; Yellow action; Red blocker; Slate information.

Contact:
  Website                   : https://www.dxbmark.com
  Email                     : support@dxbmark.com
  Phone / WhatsApp          : +971505121583
HELP
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
  shift
done

if [ "${M32_INSTALL_DRY_RUN:-0}" = "1" ]; then
  DRY_RUN=1
fi
detect_platform() {
  if [ -n "${PLATFORM}" ]; then
    printf '%s\n' "${PLATFORM}"
    return
  fi
  if [ -n "${WSL_DISTRO_NAME:-}" ] || { [ -r /proc/version ] && grep -qi microsoft /proc/version; }; then
    printf '%s\n' "wsl"
    return
  fi
  uname_s="$(uname -s 2>/dev/null || printf unknown)"
  case "${uname_s}" in
    Darwin) printf '%s\n' "macos" ;;
    Linux)
      if [ -r /etc/os-release ] && grep -Eqi 'raspbian|raspberry pi os' /etc/os-release; then
        printf '%s\n' "raspberry_pi_os"
      else
        printf '%s\n' "linux"
      fi
      ;;
    *) printf '%s\n' "linux" ;;
  esac
}

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd -P || pwd)
REPO_ROOT=$(CDPATH= cd -- "${SCRIPT_DIR}/.." 2>/dev/null && pwd -P || pwd)
PLATFORM_VALUE="$(detect_platform)"

CHECKOUT_AVAILABLE=0
if [ -d "${REPO_ROOT}/src/m32_bridge" ] && [ -f "${REPO_ROOT}/pyproject.toml" ]; then CHECKOUT_AVAILABLE=1; fi
selector_count=0
for selector in "${VERSION_SELECTION}" "${CHANNEL_SELECTION}" "${REF_SELECTION}" "${LOCAL_SELECTION}"; do
  if [ -n "${selector}" ] && [ "${selector}" != "0" ] && [ "${selector}" != "false" ]; then selector_count=$((selector_count + 1)); fi
done
if [ "${selector_count}" -gt 1 ]; then
  echo "INSTALL_SELECTION_CONFLICT: use only one of --version, --channel, --ref, or --local." >&2
  exit 2
fi
if [ -n "${VERSION_SELECTION}" ]; then
  if ! printf '%s\n' "${VERSION_SELECTION}" | grep -Eq '^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?(\+[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?$'; then
    echo "RELEASE_TAG_INVALID: --version requires strict v-prefixed SemVer." >&2
    exit 2
  fi
  INSTALL_SOURCE="github_release_asset"
elif [ -n "${REF_SELECTION}" ]; then
  if [ "${#REF_SELECTION}" -ne 40 ] || printf '%s\n' "${REF_SELECTION}" | grep -Eq '[^0-9A-Fa-f]'; then
    echo "RELEASE_SOURCE_COMMIT_INVALID: --ref requires one full 40-character hexadecimal SHA." >&2
    exit 2
  fi
  INSTALL_SOURCE="github_commit_archive"
elif [ "${LOCAL_SELECTION}" = "1" ] || [ "${LOCAL_SELECTION}" = "true" ]; then
  INSTALL_SOURCE="local_checkout"
elif [ -n "${CHANNEL_SELECTION}" ]; then
  case "${CHANNEL_SELECTION}" in
    stable|prerelease) INSTALL_SOURCE="github_release_asset" ;;
    main) INSTALL_SOURCE="github_main" ;;
    *) echo "INSTALL_CHANNEL_INVALID: use stable, prerelease, or main." >&2; exit 2 ;;
  esac
elif [ "${CHECKOUT_AVAILABLE}" = "1" ]; then
  INSTALL_SOURCE="local_checkout"
  LOCAL_SELECTION="1"
else
  INSTALL_SOURCE="github_release_asset"
  CHANNEL_SELECTION="stable"
fi
if [ "${INSTALL_SOURCE}" != "local_checkout" ]; then
  REPO_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/m32-bridge-bootstrap.XXXXXX")" || {
    echo "BOOTSTRAP_STAGING_FAILED: could not create private temporary staging." >&2
    exit 1
  }
fi

required_actions_json() {
  cat <<JSON
[
  {
    "action_id": "INSTALL_UV_USER_LOCAL",
    "title": "Install uv in user space",
    "reason": "M32 Bridge uses uv to manage Python runtime dependencies without system Python launcher assumptions.",
    "command_preview": "curl -LsSf https://astral.sh/uv/install.sh -o install-uv.sh; inspect install-uv.sh; run only after confirmation",
    "requires_confirmation": true,
    "risk_level": "user_local",
    "target_paths": ["${HOME}/.local/bin/uv"],
    "official_source_url": "https://docs.astral.sh/uv/getting-started/installation/",
    "user_can_skip": false
  }
]
JSON
}

is_tty() {
  [ -t 0 ] && [ -t 1 ]
}

ansi_or_plain() {
  case "$(terminal_color_mode)" in
    truecolor) printf '\033[38;2;249;126;26m%s\033[0m\n' "$1" ;;
    basic) printf '\033[33m%s\033[0m\n' "$1" ;;
    *) printf '%s\n' "$1" ;;
  esac
}

terminal_color_mode() {
  if ! is_tty || [ "${TERM:-dumb}" = "dumb" ] || [ "${NO_COLOR:-}" != "" ]; then
    printf '%s\n' none
    return
  fi
  case "${COLORTERM:-}" in
    truecolor|24bit) printf '%s\n' truecolor ;;
    *) printf '%s\n' basic ;;
  esac
}

tty_width() {
  cols="$(tput cols 2>/dev/null || printf 80)"
  case "${cols}" in
    ''|*[!0-9]*) printf '%s\n' 80 ;;
    *) printf '%s\n' "${cols}" ;;
  esac
}

paint_tty_lines() {
  if ! is_tty; then
    cat
    return
  fi
  width=$(( $(tty_width) - 1 ))
  if [ "${width}" -lt 20 ]; then
    width=20
  fi
  color_mode="$(terminal_color_mode)"
  while IFS= read -r line; do
    visible_len=${#line}
    if [ "${visible_len}" -gt "${width}" ]; then
      line="$(printf '%s' "${line}" | cut -c 1-"${width}")"
      visible_len=${#line}
    fi
    pad=$((width - visible_len))
    if [ "${color_mode}" = "truecolor" ]; then
      printf '\033[48;2;36;57;71m%s' "${line}"
      if [ "${pad}" -gt 0 ]; then
        printf '%*s' "${pad}" ''
      fi
      printf '\033[0m\n'
    elif [ "${color_mode}" = "basic" ]; then
      printf '\033[37m%s\033[0m\n' "${line}"
    else
      printf '%s\n' "${line}"
    fi
  done
}

installer_help() {
  cat <<'HELP'
/help - show installer sections and safe next commands
/contact - show DXBMARK support contact
/status - show installer/runtime/source/safety state
/clear - redraw the installer screen
/exit - exit the installer TTY flow
Dry-run prints the plan without writing app or launcher files.
JSON mode is for CI and never includes banners or ANSI colours.
Missing uv requires explicit user-local setup; no global py is required.
Managed Python is CPython 3.13.x through uv; system Python stays unchanged.
Website                   : https://www.dxbmark.com
Email                     : support@dxbmark.com
Phone / WhatsApp          : +971505121583
HELP
}

installer_contact() {
  cat <<'CONTACT'
DXBMARK Support
Website                   : https://www.dxbmark.com
Email                     : support@dxbmark.com
Phone / WhatsApp          : +971505121583
CONTACT
}

print_missing_uv_tty() {
  mode="status"
  if [ "${DRY_RUN}" = "1" ]; then
    mode="dry-run"
  fi
  case "$(terminal_color_mode)" in
    truecolor) printf '\033[2J\033[H\033[38;2;249;126;26m' ;;
    basic) printf '\033[2J\033[H\033[33m' ;;
  esac
  {
  cat <<TEXT
X32-BRIDGE MCP INSTALLER
Powered by DXBMARK LLC
#  ______  ______  __  __    _    ____  _  __
# |  _ \\ \\/ / __ )|  \\/  |  / \\  |  _ \\| |/ / LLC
# | | | \\  /|  _ \\| |\\/| | / _ \\ | |_) | ' /
# | |_| /  \\| |_) | |  | |/ ___ \\|  _ <| . \\
# |____/_/\\_\\____/|_|  |_/_/   \\_\\_| \\_\\_|\\_\\ dxbmark.com
User-local installer. No admin, no service, no binary package.
Type / for interactive menu | Type /help for list

System Check
  OS: ${PLATFORM_VALUE}
  architecture: $(uname -m 2>/dev/null || printf unknown)
  shell: ${SHELL:-unknown}
Download capability
  Primary tool: $(if command -v curl >/dev/null 2>&1; then printf 'curl available'; elif command -v wget >/dev/null 2>&1; then printf 'wget available'; else printf 'not available'; fi)
  wget fallback: $(if command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1; then printf 'optional, not installed'; elif command -v wget >/dev/null 2>&1; then printf available; else printf 'optional, not installed'; fi)
  Manual fallback: available
  uv status: missing
  managed Python state: not_installed
  application installed state: not_installed
  launcher state: not_installed
  Python strategy: CPython 3.13.x managed by uv; system Python unchanged; no global py required
  Runtime config: not inspected until application runtime is ready

Source Check
  install_source: ${INSTALL_SOURCE}
  source_url: ${SOURCE_URL}
  source_ref: ${SOURCE_REF}
  Source configuration: configured: github source archive
  Reachability: not_checked

Install Plan
  mode: ${mode}
  status: RUNTIME_SETUP_REQUIRED
  install_root: ${HOME}/.m32-bridge
  app_path: ${HOME}/.m32-bridge/app
  launcher_path: ${HOME}/.local/bin/m32-bridge
  user_local=true
  admin_required=false

Safety
  osc_writes_sent=0
  hardware_verified=false
  production_live_ready=false
  no /set
  no OSC writes
  no IDE or MCP client config writes
  network_scan=not_run
  console_probe=not_run

Required Actions
  INSTALL_UV_USER_LOCAL: Install uv in user space
    reason: M32 Bridge uses uv to manage Python runtime dependencies without system Python launcher assumptions.
    command: download https://astral.sh/uv/install.sh to a temporary file; run only after exact INSTALL confirmation
    confirmation_required=true

After installation
  These commands become available after the managed application runtime is installed.
  /health          Check runtime and installation readiness
  /setup           Configure a known console endpoint
  /get-info        Read information from the configured endpoint
  /verify-device   Verify the configured endpoint; no network scan
  /doctor-runtime  Diagnose local runtime issues

Commands
  /help
  /contact
  /status
  /clear
  /exit
TEXT
  } | paint_tty_lines
}

handle_missing_uv_tty_input() {
  if ! is_tty; then
    return
  fi
  if [ "${DRY_RUN}" = "1" ]; then
    return
  fi
  cat <<'SETUP'
Required Runtime Setup

uv is required to install and run M32 Bridge.
It will be installed for the current user only.
No administrator access is required.
System Python will not be changed.

Options:
  [1] Install uv user-locally
  [2] Show manual instructions
  [3] Exit
SETUP
  printf '%s' "Select [1-3]: "
  IFS= read -r answer || return
  case "${answer}" in
    /help|help)
      installer_help
      ;;
    /contact|contact)
      installer_contact
      ;;
    /status|status)
      printf '%s\n' "installer state: RUNTIME_SETUP_REQUIRED"
      printf '%s\n' "OS: ${PLATFORM_VALUE}"
      printf '%s\n' "architecture: $(uname -m 2>/dev/null || printf unknown)"
      printf '%s\n' "shell: ${SHELL:-unknown}"
      printf '%s\n' "uv: missing"
      printf '%s\n' "managed Python: not_installed"
      printf '%s\n' "application: not_installed"
      printf '%s\n' "launcher: not_installed"
      printf '%s\n' "install source: ${INSTALL_SOURCE}"
      printf '%s\n' "Source configuration: configured: github source archive"
      printf '%s\n' "Reachability: not_checked"
      printf '%s\n' "Runtime config: not inspected until application runtime is ready"
      printf '%s\n' "safety: admin_required=false, system_python_unchanged=true, network_scan=not_run, console_probe=not_run, osc_writes_sent=0"
      ;;
    /clear|clear)
      printf '\033[2J\033[H'
      print_missing_uv_tty
      ;;
    /exit|exit|quit|q)
      printf '%s\n' "status=RUNTIME_SETUP_REQUIRED"
      printf '%s\n' "No dependency action was taken."
      ;;
    1)
      bootstrap_uv_tty
      ;;
    2)
      printf '%s\n' "Download ${UV_INSTALL_URL_POSIX}, inspect it, install uv for your user, then run: uv python install ${APPROVED_PYTHON_MINOR}"
      ;;
    3)
      printf '%s\n' "status=RUNTIME_SETUP_REQUIRED"
      printf '%s\n' "No dependency action was taken."
      ;;
    *)
      printf '%s\n' "status=RUNTIME_SETUP_REQUIRED"
      printf '%s\n' "No dependency action was taken."
      ;;
  esac
}

bootstrap_uv_tty() {
  cat <<'CONFIRM'
Source
  Official installer URL: https://astral.sh/uv/install.sh

Target
  User-local uv installation paths

Managed Python
  CPython 3.13.x
  Installed and used only through uv

Changes
  Downloads uv installer to a temporary file
  Installs uv for the current user
  Installs approved managed Python if required
  May provide PATH guidance
  Does not use administrator elevation
  Does not change system Python
  Does not install wget or curl

Type INSTALL to continue.
CONFIRM
  IFS= read -r confirmation || return 1
  if [ "${confirmation}" != "INSTALL" ]; then
    printf '%s\n' "Exact INSTALL confirmation was not provided. No download or install was performed."
    return 1
  fi
  uv_temp="$(mktemp "${TMPDIR:-/tmp}/m32-uv-installer.XXXXXX")" || return 1
  trap 'rm -f "${uv_temp}"' 0 HUP INT TERM
  printf '%s\n' "URL: ${UV_INSTALL_URL_POSIX}"
  printf '%s\n' "Temporary path: ${uv_temp}"
  if command -v curl >/dev/null 2>&1; then
    curl -fLsS "${UV_INSTALL_URL_POSIX}" -o "${uv_temp}" || {
      printf '%s\n' "uv installer download failed." >&2
      rm -f "${uv_temp}"
      trap - 0 HUP INT TERM
      return 1
    }
  elif command -v wget >/dev/null 2>&1; then
    wget -q -O "${uv_temp}" "${UV_INSTALL_URL_POSIX}" || {
      printf '%s\n' "uv installer download failed." >&2
      rm -f "${uv_temp}"
      trap - 0 HUP INT TERM
      return 1
    }
  else
    printf '%s\n' "No download tool is available. Use the manual instructions." >&2
    rm -f "${uv_temp}"
    trap - 0 HUP INT TERM
    return 1
  fi
  if [ ! -s "${uv_temp}" ]; then
    printf '%s\n' "Downloaded uv installer is empty." >&2
    rm -f "${uv_temp}"
    trap - 0 HUP INT TERM
    return 1
  fi
  /bin/sh "${uv_temp}" || {
    printf '%s\n' "uv installer execution failed." >&2
    rm -f "${uv_temp}"
    trap - 0 HUP INT TERM
    return 1
  }
  rm -f "${uv_temp}"
  trap - 0 HUP INT TERM
  UV_BIN="${HOME}/.local/bin/uv"
  if [ ! -x "${UV_BIN}" ]; then
    printf '%s\n' "uv installation completed but the expected user-local executable is unavailable: ${UV_BIN}" >&2
    return 1
  fi
  PATH="${HOME}/.local/bin:${PATH}"
  export PATH
  "${UV_BIN}" --version
  UV_MANAGED_PYTHON=1 "${UV_BIN}" python install "${APPROVED_PYTHON_MINOR}" || {
    printf '%s\n' "Managed CPython 3.13 installation failed." >&2
    return 1
  }
  managed_python="$(UV_MANAGED_PYTHON=1 "${UV_BIN}" python find --managed-python "${APPROVED_PYTHON_MINOR}" 2>/dev/null || true)"
  if [ -z "${managed_python}" ] || [ ! -x "${managed_python}" ]; then
    printf '%s\n' "Managed CPython 3.13 could not be rediscovered." >&2
    return 1
  fi
  "${managed_python}" --version
  printf '%s\n' "Managed Python path: ${managed_python}"
  return 0
}

print_missing_uv_json() {
  APP_PATH="${HOME}/.m32-bridge/app"
  LAUNCHER_PATH="${HOME}/.local/bin/m32-bridge"
  cat <<JSON
{
  "ok": false,
  "status": "RUNTIME_SETUP_REQUIRED",
  "platform": "${PLATFORM_VALUE}",
  "app_path": "${APP_PATH}",
  "launcher_path": "${LAUNCHER_PATH}",
  "install_root": "${HOME}/.m32-bridge",
  "requires_admin": false,
  "admin_required": false,
  "user_local": true,
  "global_py_required": false,
  "global_python_required": false,
  "uv_required": true,
  "uv_detected": false,
  "python_required": true,
  "python_managed_by_uv": true,
  "approved_python_minor": "${APPROVED_PYTHON_MINOR}",
  "project_python_range": "${PROJECT_PYTHON_RANGE}",
  "system_python_modified": false,
  "global_python_installed": false,
  "default_python_aliases_installed": false,
  "installer_can_continue": false,
  "confirmation_required": true,
  "uv_status": "manual_action_required",
  "required_actions": $(required_actions_json),
  "osc_writes_sent": 0,
  "hardware_verified": false,
  "production_live_ready": false,
  "application_version": null,
  "application_version_source": "not_resolved",
  "requested_selection": "${VERSION_SELECTION:-${CHANNEL_SELECTION:-${REF_SELECTION:-local}}}",
  "install_source": "${INSTALL_SOURCE}",
  "source_url": "${SOURCE_URL}",
  "source_ref": "${SOURCE_REF}",
  "path_updated": false,
  "recommendations": [
    "Install uv in user space, then rerun this installer.",
    "No system-wide interpreter or \`py\` launcher is required.",
    "POSIX bootstrap supports curl first, wget fallback, or manual download."
  ]
}
JSON
}

write_secure_bootstrap_helper() {
  helper_path="$1"
  PYTHON_PAYLOAD="${SECURE_BOOTSTRAP_PAYLOAD}"   "${UV_BIN}" run --managed-python --python "${APPROVED_PYTHON_MINOR}" --no-build --no-project     python -c 'import base64,gzip,os,pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes(gzip.decompress(base64.b64decode(os.environ["PYTHON_PAYLOAD"])))'     "${helper_path}"
}

bootstrap_plan_value() {
  key="$1"
  "${UV_BIN}" run --managed-python --python "${APPROVED_PYTHON_MINOR}" --no-build --no-project     python -c 'import json,sys; value=json.load(open(sys.argv[1], encoding="utf-8")).get(sys.argv[2]); print("" if value is None else value)'     "${BOOTSTRAP_PLAN_PATH}" "${key}"
}

prepare_remote_source() {
  mkdir -p "${REPO_ROOT}"
  helper="${REPO_ROOT}/secure_bootstrap.py"
  BOOTSTRAP_PLAN_PATH="${REPO_ROOT}/bootstrap-plan.json"
  write_secure_bootstrap_helper "${helper}" || return 1

  if [ -n "${VERSION_SELECTION}" ]; then
    set -- --version "${VERSION_SELECTION}"
  elif [ -n "${REF_SELECTION}" ]; then
    set -- --ref "${REF_SELECTION}"
  else
    set -- --channel "${CHANNEL_SELECTION:-stable}"
  fi
  if [ "${DRY_RUN}" = "1" ]; then
    set -- "$@" --dry-run
  fi

  if ! "${UV_BIN}" run --managed-python --python "${APPROVED_PYTHON_MINOR}" --no-build --no-project       python "${helper}" --surface posix --output-root "${REPO_ROOT}" "$@"       > "${BOOTSTRAP_PLAN_PATH}"; then
    cat "${BOOTSTRAP_PLAN_PATH}" >&2 2>/dev/null || true
    return 1
  fi

  SOURCE_COMMIT="$(bootstrap_plan_value source_commit)"
  SOURCE_REF="$(bootstrap_plan_value source_ref)"
  SOURCE_URL="$(bootstrap_plan_value source_archive_url)"
  RELEASE_TAG="$(bootstrap_plan_value release_tag)"

  if [ "${DRY_RUN}" = "1" ]; then
    if [ "${JSON_OUTPUT}" = "1" ]; then
      cat "${BOOTSTRAP_PLAN_PATH}"
    else
      "${UV_BIN}" run --managed-python --python "${APPROVED_PYTHON_MINOR}" --no-build --no-project         python -c 'import json,sys; p=json.load(open(sys.argv[1], encoding="utf-8")); print("M32 Bridge remote dry-run"); [print(f"{k}: {p.get(k)}") for k in ("status","requested_selection","install_source","release_tag","source_commit","application_version","source_archive_url","archive_checksum_status","identity_status")]; print("admin_required=false"); print("system_python_modified=false"); print("network_scan=not_run"); print("console_probe=not_run"); print("osc_writes_sent=0")'         "${BOOTSTRAP_PLAN_PATH}"
    fi
    return 2
  fi

  verified_root="$(bootstrap_plan_value source_root)"
  if [ -z "${verified_root}" ] || [ ! -f "${verified_root}/pyproject.toml" ] || [ ! -f "${verified_root}/uv.lock" ] || [ ! -d "${verified_root}/src/m32_bridge" ]; then
    echo "BOOTSTRAP_PLAN_INVALID: verified source root is incomplete." >&2
    return 1
  fi
  REPO_ROOT="${verified_root}"
  return 0
}

cleanup_remote_source() {
  target="${BOOTSTRAP_SOURCE_ROOT:-}"
  case "${target}" in
    "${TMPDIR:-/tmp}"/m32-bridge-bootstrap.*)
      if [ -d "${target}" ]; then
        rm -r -- "${target}"
      fi
      ;;
  esac
}

RUNTIME_MODULE="m32_bridge.installer.script_runtime"
set -- python -m "${RUNTIME_MODULE}" --surface posix --platform "${PLATFORM_VALUE}"
if [ -n "${VERSION_SELECTION}" ]; then set -- "$@" --version "${VERSION_SELECTION}"; fi
if [ -n "${CHANNEL_SELECTION}" ]; then set -- "$@" --channel "${CHANNEL_SELECTION}"; fi
if [ -n "${REF_SELECTION}" ]; then set -- "$@" --ref "${REF_SELECTION}"; fi
if [ "${LOCAL_SELECTION}" = "1" ] || [ "${LOCAL_SELECTION}" = "true" ]; then set -- "$@" --local; fi
if [ -n "${TARGET_VERSION}" ]; then set -- "$@" --target-version "${TARGET_VERSION}"; fi
if [ "${DRY_RUN}" = "1" ]; then
  set -- "$@" --dry-run
fi
if [ "${JSON_OUTPUT}" = "1" ]; then
  set -- "$@" --json
fi
if [ "${JSON_OUTPUT}" != "1" ] && is_tty; then
  set -- "$@" --tty --color
fi

UV_BIN="$(command -v uv 2>/dev/null || true)"
if [ -z "${UV_BIN}" ] && [ "${JSON_OUTPUT}" != "1" ] && [ "${DRY_RUN}" != "1" ] && is_tty; then
  print_missing_uv_tty
  if handle_missing_uv_tty_input; then
    UV_BIN="$(command -v uv 2>/dev/null || true)"
    if [ -z "${UV_BIN}" ] && [ -x "${HOME}/.local/bin/uv" ]; then
      UV_BIN="${HOME}/.local/bin/uv"
    fi
  fi
fi

if [ -n "${UV_BIN}" ]; then
  if [ "${INSTALL_SOURCE}" != "local_checkout" ]; then
    BOOTSTRAP_SOURCE_ROOT="${REPO_ROOT}"
    trap 'cleanup_remote_source' 0 HUP INT TERM
    bootstrap_status=0
    prepare_remote_source || bootstrap_status=$?
    if [ "${bootstrap_status}" -eq 2 ]; then
      exit 0
    fi
    if [ "${bootstrap_status}" -ne 0 ]; then
      exit 1
    fi
  fi
  set -- "$@" --source-root "${REPO_ROOT}"
  if [ -n "${BOOTSTRAP_PLAN_PATH:-}" ]; then set -- "$@" --bootstrap-plan "${BOOTSTRAP_PLAN_PATH}"; fi
  if [ ! -f "${REPO_ROOT}/uv.lock" ]; then
    echo "uv.lock is required for reproducible frozen runtime execution. Refusing unfrozen install." >&2
    exit 1
  fi
  if [ "${DRY_RUN}" != "1" ]; then
    set -- "$@" --bootstrap-apply --uv-bin "${UV_BIN}"
  fi
  PYTHONPATH_VALUE="${REPO_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
  if [ "${M32_INSTALL_ASSUME_UV:-}" = "installed_user_local" ] && [ -x "${REPO_ROOT}/.venv/bin/python" ]; then
    shift
    PYTHONPATH="${PYTHONPATH_VALUE}" "${REPO_ROOT}/.venv/bin/python" "$@"
  else
    if [ -z "${UV_CACHE_DIR:-}" ]; then
      mkdir -p "${DEFAULT_UV_CACHE_DIR}"
      UV_CACHE_DIR="${DEFAULT_UV_CACHE_DIR}"
      export UV_CACHE_DIR
    fi
    PYTHONPATH="${PYTHONPATH_VALUE}" UV_MANAGED_PYTHON=1 M32_INSTALL_UV_BIN="${UV_BIN}" \
      "${UV_BIN}" run --managed-python --python "${APPROVED_PYTHON_MINOR}" --no-build --no-project "$@"
  fi
else
  if [ "${JSON_OUTPUT}" = "1" ]; then
    print_missing_uv_json
  elif is_tty && [ "${DRY_RUN}" = "1" ]; then
    print_missing_uv_tty
  else
    echo "M32 Bridge installer status"
    if [ "${DRY_RUN}" = "1" ]; then
      echo "mode: dry-run"
    else
      echo "mode: status"
    fi
    echo "status: RUNTIME_SETUP_REQUIRED"
    echo "install_root: ${HOME}/.m32-bridge"
    echo "app_path: ${HOME}/.m32-bridge/app"
    echo "launcher_path: ${HOME}/.local/bin/m32-bridge"
    echo "install_source: ${INSTALL_SOURCE}"
    echo "source_url: ${SOURCE_URL}"
    echo "user_local: true"
    echo "admin_required=false"
    echo "global_py_required=false"
    echo "global_python_required=false"
    echo "approved_python_minor=${APPROVED_PYTHON_MINOR}"
    echo "project_python_range=${PROJECT_PYTHON_RANGE}"
    echo "system_python_modified=false"
    echo "installer_can_continue=false"
    echo "uv_status=manual_action_required"
    echo "hardware_verified=false"
    echo "production_live_ready=false"
    echo "osc_writes_sent=0"
    echo "Install uv in user space, then rerun this installer. No system-wide interpreter or \`py\` launcher is required."
    echo "Post-install checks: m32-bridge health, m32-bridge setup, m32-bridge get-info, m32-bridge detect-device, m32-bridge doctor-runtime."
  fi
  exit 1
fi
