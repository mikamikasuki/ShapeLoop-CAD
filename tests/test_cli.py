import pytest
from typer.testing import CliRunner
from shapeloop.cli import app

@pytest.mark.parametrize('command',['build','edit','check','export','compare','accept','undo','redo'])
def test_documented_project_option(command):
    runner=CliRunner()
    result=runner.invoke(app,[command,'--help'],color=False)
    assert result.exit_code==0,result.output
    assert '--project' in result.output

def test_missing_project_message_is_actionable():
    result=CliRunner().invoke(app,['check','--project','/nonexistent/shapeloop-project.json'])
    assert result.exit_code==2 and 'Project pointer not found' in result.output
