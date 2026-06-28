import os

def fix_app():
    with open('app.py', 'r', encoding='utf-8') as f:
        content = f.read()
        
    content = content.replace("\\n", "\n")
    
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == "__main__":
    fix_app()
